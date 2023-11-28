import contextlib
import sqlite3
import typing
import collections
import os
import httpx
import datetime
import logging.config

from fastapi import Depends, HTTPException, APIRouter, status, Query
from pydantic_settings import BaseSettings
from users.users_schemas import *
from users.users_hash import hash_password, verify_password

class Settings(BaseSettings, env_file=".env", extra="ignore"):
    users_database: str
    users_logging_config: str

DEBUG = False

settings = Settings()
router = APIRouter()

primary_database = "var/primary/fuse/users.db"
secondary_database = "var/secondary/fuse/users.db"
tertiary_database = "var/tertiary/fuse/users.db"

# Used for the search endpoint
SearchParam = collections.namedtuple("SearchParam", ["name", "operator"])
SEARCH_PARAMS = [
    SearchParam(
        "uid",
        "=",
    ),
    SearchParam(
        "name",
        "LIKE",
    ),
    SearchParam(
        "role",
        "LIKE",
    ),
]

# The next two functions handles JWT claim
def expiration_in(minutes):
    creation = datetime.datetime.now(tz=datetime.timezone.utc)
    expiration = creation + datetime.timedelta(minutes=minutes)
    return creation, expiration


def generate_claims(username, user_id, roles):
    _, exp = expiration_in(20)

    claims = {
        "aud": "krakend.local.gd",
        "iss": "auth.local.gd",
        "sub": username,
        "jti": str(user_id),
        "roles": roles,
        "exp": int(exp.timestamp()),
    }
    token = {
        "access_token": claims,
        "refresh_token": claims,
        "exp": int(exp.timestamp()),
    }

    return token

def get_logger():
    return logging.getLogger(__name__)

# Flag to track the last database used for read operations
last_read_db = None  # Start with None to use secondary database first

# Connect to the appropriate database based on the endpoint
def get_db_read(logger: logging.Logger = Depends(get_logger)):
    
    if DEBUG:
        print("Using read-only db")

    # Database availability check
    available_databases = []

    if os.path.exists(primary_database):
        available_databases.append(primary_database)

    if os.path.exists(secondary_database):
        available_databases.append(secondary_database)

    if os.path.exists(tertiary_database):
        available_databases.append(tertiary_database)

    if not available_databases:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="All databases are unavailable")
    
    else:
        global last_read_db

        # check if secondary and tertiary are available
        if available_databases[1] and available_databases[2]:
            # if so, check last db used, switch to other db
            if last_read_db == secondary_database:
                last_read_db = tertiary_database
                if DEBUG:
                    print("tertiary db used")
            else:
                last_read_db = secondary_database
                if DEBUG:
                    print("secondary db used")
        # else if secondary is available and tertiary is not, set to secondary
        elif available_databases[1] and not available_databases[2]:
            last_read_db = secondary_database
            if DEBUG:
                    print("secondary db used")
        # else if secondary is not available and tertiary is, set to tertiary
        elif not available_databases[1] and available_databases[2]:
            last_read_db = tertiary_database
            if DEBUG:
                    print("tertiary db used")
        # else set to primary as a last resort
        else:
            last_read_db = primary_database
            if DEBUG:
                    print("primary db used")

        with contextlib.closing(sqlite3.connect(last_read_db, check_same_thread=False)) as db:
            db.row_factory = sqlite3.Row
            db.set_trace_callback(logger.debug)
            yield db

def get_db_write(logger: logging.Logger = Depends(get_logger)):

    if DEBUG:
        print("Using write allowed db")

    if os.path.exists(primary_database):
        with contextlib.closing(sqlite3.connect(primary_database, check_same_thread=False)) as db:
            db.row_factory = sqlite3.Row
            db.set_trace_callback(logger.debug)
            yield db
    else:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Database unavailable")

logging.config.fileConfig(settings.users_logging_config, disable_existing_loggers=False)

#==========================================Users==================================================

# The login enpoint, where JWT validation needs to occur
@router.post("/users/login", tags=['Users'])
def get_user_login(user: User, db: sqlite3.Connection = Depends(get_db_read)):
    cursor = db.cursor()

    cursor.execute(
        """
        SELECT * FROM users WHERE name = ?
        """, (user.name,)
    )
    user_data = cursor.fetchone()
    
    # Check if user exists
    if not user_data:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid username")

    # Verify the password
    if not verify_password(user.password, user_data['password']):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid password")
    
    # Retrieve roles for the student
    cursor.execute(
           """
           SELECT role FROM user_role
           JOIN role ON user_role.role_id = role.rid
           JOIN users ON user_role.user_id = users.uid
           WHERE user_id = ?
           """,
           (user_data["uid"],)
       )
    roles_data = cursor.fetchall()

    roles = [role["role"] for role in roles_data]

    #Issue JWT token
    token_data = generate_claims(user_data['name'], user_data['uid'], roles)
    return token_data


# Create new user endpoint
@router.post("/users/register", tags=['Users'])
async def register_new_user(user: User, db: sqlite3.Connection = Depends(get_db_write)):
    cursor = db.cursor()
    cursor.execute(
        """
        SELECT * FROM users WHERE name = ?
        """, (user.name,)
    )
    user_data = cursor.fetchone()
    
    # Check if user exists
    if user_data:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Username already exists")

    # Hash the password before storing it
    password_hash = hash_password(user.password)

    #Store new user data in DB
    cursor.execute(
        """
        INSERT INTO users (name, password)
        VALUES (?, ?)
        """, (user.name, password_hash)
    )

    #Give new user default role of 'student'
    cursor.execute(
        """
        SELECT * FROM users WHERE name = ?
        """, (user.name,)
    )
    user_data = cursor.fetchone()

    cursor.execute(
        """
        INSERT INTO user_role (user_id, role_id)
        VALUES (?, ?)
        """, (user_data['uid'], 1)
    )

    db.commit()

    #call enrollment endpoint /registrar/create_user
    enrollment_URL = "http://localhost:5000/registrar/create_user"
    
    # Make an HTTP request to the enrollment service using the app instance
    user_data_to_send = {
        "name": user.name,
        "roles": ["student"],
    }

    # Make an HTTP request to the enrollment service
    async with httpx.AsyncClient() as client:
        response = await client.post(f"{enrollment_URL}", json=user_data_to_send)

    if response.status_code == 200:
        return {"message": "User created successfully"}
    else:
        raise HTTPException(status_code=response.status_code, detail="Failed to create user in enrollment service")


# Have a user check their password
@router.get("/users/check_password", tags=['Users'])
def get_user_password(username: str = Query(..., title="Username", description="Your username"),
    password: str = Query(..., title="Password", description="Your password"),
    db: sqlite3.Connection = Depends(get_db_read)):

    # Query the database to retrieve the user's password hash
    cursor = db.cursor()
    cursor.execute(
        """
        SELECT password FROM users WHERE name = ?
        """, (username,)
    )
    q = cursor.fetchone()

    # Check if user exists
    if not q:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    
    # Check the password
    password_hash = q[0]

    if verify_password(password, password_hash):
        return {"message": "Password is correct"}
    else:
        return {"message": "Password is incorrect"}
    

#==========================================Test Endpoints==================================================

# None of the following endpoints are required (I assume), but might be helpful
# for testing purposes


# Search for specific users based on optional parameters,
# if no parameters are given, returns all users
@router.get("/debug/search", tags=['Debug'])
def search_for_users(uid: typing.Optional[str] = None,
                 name: typing.Optional[str] = None,
                 role: typing.Optional[str] = None,
                 db: sqlite3.Connection = Depends(get_db_read)):
    
    users_info = []

    sql = """SELECT * FROM users
             LEFT JOIN user_role ON users.uid = user_role.user_id
             LEFT JOIN role ON user_role.role_id = role.rid"""
    
    conditions = []
    values = []
    arguments = locals()

    for param in SEARCH_PARAMS:
        if arguments[param.name]:
            if param.operator == "=":
                conditions.append(f"{param.name} = ?")
                values.append(arguments[param.name])
            else:
                conditions.append(f"{param.name} LIKE ?")
                values.append(f"%{arguments[param.name]}%")
    
    if conditions:
        sql += " WHERE "
        sql += " AND ".join(conditions)

    cursor = db.cursor()

    cursor.execute(sql, values)
    search_data = cursor.fetchall()

    if not search_data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No users found that match search parameters")

    previous_uid = None
    for user in search_data:
        cursor.execute(
            """
            SELECT role FROM users 
            JOIN role ON user_role.role_id = role.rid
            JOIN user_role ON users.uid = user_role.user_id
            WHERE uid = ?
            """,
            (user["uid"],)
        )
        roles_data = cursor.fetchall()
        roles = [role["role"] for role in roles_data]

        if previous_uid != user["uid"]:
            user_information = User_info(
                uid=user["uid"],
                name=user["name"],
                password=user["password"],
                roles=roles
            )
            users_info.append(user_information)
        previous_uid = user["uid"]

    return {"users" : users_info}


# Change a user's role
@router.put("/debug/users/{user_id}/role_change", tags=['Debug'])
def change_user_role(user_id: int, roles: List[str], db: sqlite3.Connection = Depends(get_db_write)):
    cursor = db.cursor()

    # Check if exist
    cursor.execute(
        """
        SELECT * FROM users WHERE uid = ?
        """, (user_id,)
    )
    user_data = cursor.fetchone()

    if not user_data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    # Delete old role data
    cursor.execute(
        """
        DELETE FROM user_role WHERE user_id = ?
        """, (user_id,)
    )

    # Update new role data
    for role in roles:
        
        cursor.execute(
        """
        SELECT rid FROM role WHERE role = ?
        """, (role,)
        )
        role_data = cursor.fetchone()

        # Check if valid role was given
        if not role_data:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Role not found")
        
        cursor.execute(
        """
        INSERT INTO user_role (user_id, role_id)
        VALUES (?, ?)
        """, (user_id, role_data['rid'])
        )

    db.commit()

    return {"message": "Roles changed successfully"}  
