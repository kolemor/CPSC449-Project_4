import logging.config
import boto3
import redis

from fastapi import Depends, HTTPException, APIRouter, status, Request
from typing import Optional
from boto3.dynamodb.conditions import Key, Attr
from enrollment.enrollment_schemas import *
from enrollment.enrollment_dynamo import Enrollment, PartiQL
from enrollment.enrollment_redis import Waitlist

settings = Settings()
router = APIRouter()

CLASS_TABLE = "enrollment_class"
USER_TABLE = "enrollment_user"
DEBUG = False
FREEZE = False
MAX_WAITLIST = 3

def get_logger():
    return logging.getLogger(__name__)

# Connect to DynamoDB
dynamodb = boto3.resource("dynamodb", endpoint_url="http://localhost:5500")

def get_table_resource(dynamodb, table_name):
    return dynamodb.Table(table_name)

# Create wrapper for PartiQL queries
wrapper = PartiQL(dynamodb)

# Connect to Redis
r = redis.Redis(db=1)

# Create class items
wl = Waitlist
enrollment = Enrollment(dynamodb)

logging.config.fileConfig(
    settings.enrollment_logging_config, disable_existing_loggers=False
)


# ==========================================students==================================================


# gets available classes for a student
@router.get("/students/{student_id}/classes", tags=["Student"])
def get_available_classes(student_id: int, request: Request):

    # User Authentication
    if request.headers.get("X-User"):
        current_user = int(request.headers.get("X-User"))

        roles_string = request.headers.get("X-Roles")
        current_roles = roles_string.split(",")

        r_flag = True
        # Check if the current user's role matches 'registrar'
        for role in current_roles:
            if role == "registrar":
                r_flag = False

        # Check if the current user's id matches the requested student_id
        if r_flag:
            if current_user != student_id:
                raise HTTPException(
                    status_code=403, detail="Access forbidden, wrong user"
                )

    # Fetch student data from db
    student_data = enrollment.get_user_item(student_id)

    # Check if exist
    if not student_data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Student not found"
        )

    waitlist_count = wl.get_waitlist_count(student_id)

    # If max waitlist, don't show full classes with open waitlists
    if waitlist_count >= MAX_WAITLIST:
        output = wrapper.run_partiql_statement(
            f'SELECT * FROM "{CLASS_TABLE}" WHERE current_enroll <= max_enroll'
        )

    # Else show all open classes or full classes with open waitlists
    else:
        # All classes have a max_enroll value of 30, and a max waitlist value of 15,
        # so 30 + 15 = 45. Technically classes can be created with any max_enroll value,
        # but I cant use partiql with arithmatic, for example I cant do
        # "WHERE current_enroll < (max_enroll + 15)". So for now its just 45
        output = wrapper.run_partiql_statement(
            f'SELECT * FROM "{CLASS_TABLE}" WHERE current_enroll < 45',
        )

    # Create a list to store the Class instances
    class_instances = []

    # Iterate through the query results and create Class instances
    for item in output["Items"]:
        # get instructor information
        result = wrapper.run_partiql(
            f'SELECT * FROM "{USER_TABLE}" WHERE id=?', [item["instructor_id"]]
        )
        # Get waitlist information
        if item["current_enroll"] > item["max_enroll"]:
            current_enroll = item["max_enroll"]
            waitlist = item["current_enroll"] - item["max_enroll"]
        else:
            current_enroll = item["current_enroll"]
            waitlist = 0
        # Create the class instance
        class_instance = Class_Enroll(
            id=item["id"],
            name=item["name"],
            course_code=item["course_code"],
            section_number=item["section_number"],
            current_enroll=current_enroll,
            max_enroll=item["max_enroll"],
            department=item["department"],
            instructor=Instructor(
                id=item["instructor_id"], name=result["Items"][0]["name"]
            ),
            current_waitlist=waitlist,
            max_waitlist=15,
        )
        class_instances.append(class_instance)
    
    # Sort the class_instances list based on the id attribute
    class_instances = sorted(class_instances, key=lambda x: x.id)

    return {"Classes": class_instances}


# Enrolls a student into an available class,
# or will automatically put the student on an open waitlist for a full class
@router.post("/students/{student_id}/classes/{class_id}/enroll", tags=["Student"])
def enroll_student_in_class(student_id: int, class_id: int, request: Request):

    class_table = get_table_resource(dynamodb, CLASS_TABLE)

    # User Authentication
    if request.headers.get("X-User"):

        current_user = int(request.headers.get("X-User"))

        roles_string = request.headers.get("X-Roles")
        current_roles = roles_string.split(",")

        r_flag = True
        # Check if the current user's role matches 'registrar'
        for role in current_roles:
            if role == "registrar":
                r_flag = False

        # Check if the current user's id matches the requested student_id
        if r_flag:
            if current_user != student_id:
                raise HTTPException(
                    status_code=403, detail="Access forbidden, wrong user"
                )

    # Fetch student data from db
    student_data = enrollment.get_user_item(student_id)

    # Fetch class data from db
    class_data = enrollment.get_class_item(class_id)

    # Check if the class and student exists in the database
    if not student_data or not class_data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Student or Class not found"
        )

    # Check if student is already enrolled in the class
    # check the information in the table
    for enrolled_student_id in class_data.get("enrolled", []):
        if student_id == enrolled_student_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Student is already enrolled in this class or currently on waitlist",
            )

    new_enrollment = class_data.get("current_enroll", 0) + 1

    # Check if the class is full, add student to waitlist if no
    ## code goes here
    if new_enrollment >= class_data.get("max_enroll", 0):
        # freeze is in place
        if not FREEZE:
            waitlist_count = wl.get_waitlist_count(student_id)
            if (
                waitlist_count < MAX_WAITLIST
                and new_enrollment < class_data.get("max_enroll", 0) + 15
            ):
                wl.add_waitlists(class_id, student_id)
                return {"message": "Student added to the waitlist"}
            else:
                return {
                    "message": "Unable to add student to waitlist due to already having the maximum number of waitlists"
                }
        else:
            return {
                "message": "Unable to add student to waitlist due to administrative freeze"
            }
        
    # Increment enrollment number in the database
    class_table.update_item(
        Key={"id": class_id},
        UpdateExpression="SET current_enroll = :new_enrollment",
        ExpressionAttributeValues={":new_enrollment": new_enrollment},
    )

    # Add student to enrolled class in the database
    class_table.update_item(
        Key={"id": class_id},
        UpdateExpression="SET enrolled = list_append(enrolled, :student_id)",
        ExpressionAttributeValues={":student_id": [student_id]},
    )

    dropped = class_data.get("dropped", [])
    new_dropped = [student_id for student_id in dropped if student_id != student_id]
    class_table.update_item(
        Key={"id": class_id},
        UpdateExpression="SET dropped = :dropped",
        ExpressionAttributeValues={":dropped": new_dropped},
    )

    return {"message": "Student successfully enrolled in class"}


# Have a student drop a class they're enrolled in
@router.put("/students/{student_id}/classes/{class_id}/drop/", tags=["Student"])
def drop_student_from_class(student_id: int, class_id: int, request: Request):

    class_table = get_table_resource(dynamodb, CLASS_TABLE)

    # user authentication
    if request.headers.get("X-User"):
        current_user = int(request.headers.get("X-User"))

        roles_string = request.headers.get("X-Roles")
        current_roles = roles_string.split(",")

        r_flag = True
        # Check if the current user's role matches 'registrar'
        for role in current_roles:
            if role == "registrar":
                r_flag = False

        # Check if the current user's id matches the requested student_id
        if r_flag:
            if current_user != student_id:
                raise HTTPException(
                    status_code=403, detail="Access forbidden, wrong user"
                )

    # fetch data for the user
    student_data = enrollment.get_user_item(student_id)

    # fetch data for the class
    class_data = enrollment.get_class_item(class_id)

    # Check if the class and student exists in the database
    if not student_data or not class_data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Student or Class not found"
        )

    # fetch enrollment information
    enrollment_data = wrapper.run_partiql(
        f'SELECT * FROM "{CLASS_TABLE}" WHERE id=?', [class_id]
    )

    # fetch waitlist information
    waitlist_data = wl.is_student_on_waitlist(student_id, class_id)

    # check if the student is enrolled or on the waitlist
    for item in enrollment_data["Items"]:
        check_enroll = item.get("enrolled", [])
        if student_id not in check_enroll or waitlist_data:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Student is not enrolled in the class",
            )

    # remove student from class
    for item in enrollment_data["Items"]:
        # store the student that is enrolled
        student_enroll = item.get("enrolled", [])
        if student_id in student_enroll:
            # remove student from enrolled
            student_enroll.remove(student_id)
            # udpate enrolled table with the removed student
            class_table.update_item(
                Key={"id": class_id},
                UpdateExpression="SET enrolled = :enrolled",
                ExpressionAttributeValues={":enrolled": student_enroll},
            )

    # Update dropped table
    class_table.update_item(
        Key={"id": class_id},
        UpdateExpression="SET dropped = list_append(dropped, :student_id)",
        ExpressionAttributeValues={":student_id": [student_id]},
    )

    return {"message": "Student successfully dropped class"}


# ==========================================wait list==========================================
# Get all waiting lists for a student
@router.get("/waitlist/students/{student_id}", tags=["Waitlist"])
def view_waiting_list(student_id: int, request: Request):

    if request.headers.get("X-User"):
        current_user = int(request.headers.get("X-User"))

        roles_string = request.headers.get("X-Roles")
        current_roles = roles_string.split(",")

        r_flag = True
        # Check if the current user's role matches 'registrar'
        for role in current_roles:
            if role == "registrar":
                r_flag = False

        # Check if the current user's id matches the requested student_id
        if r_flag:
            if current_user != student_id:
                raise HTTPException(
                    status_code=403, detail="Access forbidden, wrong user"
                )

    # Retrieve waitlist entries for the specified student from redis
    waitlist_data = wl.get_student_waitlist(student_id)

    # Check if exist
    if not waitlist_data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Student is not on a waitlist",
        )

    # fetch all relevant waitlist information for student
    student_class_id = waitlist_data.keys()

    # Create a list to store the Waitlist_Student instances
    waitlist_list = []

    # Iterate through the query results and create Waitlist_Student instances
    for cid in student_class_id:
        # get waitlist information
        waitlist_info = Waitlist_Student(
            class_id=cid, waitlist_position=waitlist_data[cid]
        )
        waitlist_list.append(waitlist_info)

    return {"Waitlists": waitlist_list}


# remove a student from a waiting list
@router.put(
    "/waitlist/students/{student_id}/classes/{class_id}/drop", tags=["Waitlist"]
)
def remove_from_waitlist(student_id: int, class_id: int, request: Request):

    if request.headers.get("X-User"):
        current_user = int(request.headers.get("X-User"))

        roles_string = request.headers.get("X-Roles")
        current_roles = roles_string.split(",")

        r_flag = True
        # Check if the current user's role matches 'registrar'
        for role in current_roles:
            if role == "registrar":
                r_flag = False

        # Check if the current user's id matches the requested student_id
        if r_flag:
            if current_user != student_id:
                raise HTTPException(
                    status_code=403, detail="Access forbidden, wrong user"
                )

    # get student information
    student_data = wl.get_student_waitlist(student_id)

    # check if student exists
    if not student_data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Student not on a waitlist"
        )

    # get class information
    student_class_id = student_data.keys()
    cid = str(class_id)

    # check if the student is in the waitlist
    if cid not in student_class_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, 
            detail="Student is not on the waiting list for this class"
        )

    # Delete student from waitlist enrollment
    wl.remove_student_from_waitlists(student_id, class_id)

    return {"message": "Student removed from the waiting list"}


# Get a list of students on a waitlist for a particular class that
# a specific instructor teaches
@router.get(
    "/waitlist/instructors/{instructor_id}/classes/{class_id}", tags=["Waitlist"]
)
def view_current_waitlist(instructor_id: int, class_id: int, request: Request):

    if request.headers.get("X-User"):
        current_user = int(request.headers.get("X-User"))

        roles_string = request.headers.get("X-Roles")
        current_roles = roles_string.split(",")

        r_flag = True
        # Check if the current user's role match2es 'registrar'
        for role in current_roles:
            if role == "registrar":
                r_flag = False

        # Check if the current user's id matches the requested instructor_id
        if r_flag:
            if current_user != instructor_id:
                raise HTTPException(
                    status_code=403, detail="Access forbidden, wrong user"
                )

    # Getting the instructors id
    user = get_table_resource(dynamodb, USER_TABLE)
    user_response = user.get_item(Key={"id": instructor_id})
    instructor_data = user_response.get("Item")

    # Getting the Instructor class
    classes = get_table_resource(dynamodb, CLASS_TABLE)
    class_response = classes.get_item(Key={"id": class_id})
    class_data = class_response.get("Item")

    if not class_data or not instructor_data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Instructor or Class not found",
        )

    # fetch data from the instructor
    instructor_data = wrapper.run_partiql(
        f"SELECT * FROM {CLASS_TABLE} WHERE instructor_id = ? AND id = ?",
        [instructor_id, class_id],
    )

    # Grabbing the first item in the list
    if "Items" in instructor_data and instructor_data["Items"]:
        retrieved_instructor_id = instructor_data["Items"][0].get("instructor_id")

        # varifies that the instructor id matches the one provided
        if retrieved_instructor_id != instructor_id:
            # chcek if the instructor is assigned to the class
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Instructor not assigned to this class",
            )

    # Get the waitlist information for the class
    class_waitlist_key = "class:{}:waitlist"
    waitlist_data = r.zrange(
        class_waitlist_key.format(class_id), 0, -1, withscores=True
    )

    # check if the waitlist class exists in redis
    if not waitlist_data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Class does not have a waitlist",
        )

    # Create a list to store the Waitlist_Instructor instances
    waitlist_list = []

    # Iterate through the query results and create Waitlist_Instructor instances
    for student_id, score in waitlist_data:
        # Convert binary data to integers
        student_id = int(student_id.decode("utf-8"))

        # Fetch student name based on student ID
        result = wrapper.run_partiql(
            f'SELECT * FROM "{USER_TABLE}" WHERE id=?', [student_id]
        )

        # Check if the result has items and fetch the student name
        if "Items" in result and result["Items"]:
            student_name = result["Items"][0]["name"]
        else:
            student_name = ""

        # Create Waitlist_Instructor instance
        waitlist_info = Waitlist_Instructor(
            student=Student(id=student_id, name=student_name),
            waitlist_position=float(score) if "." in str(score) else int(score),
        )
        waitlist_list.append(waitlist_info)

    return {"Waitlist": waitlist_list}


# ==========================================Instructor==================================================
# view current enrollment for class
@router.get(
    "/instructors/{instructor_id}/classes/{class_id}/enrollment", tags=["Instructor"]
)
def get_instructor_enrollment(instructor_id: int, class_id: int, request: Request):
    # Checks for the correct role. In this case, Instructor role is needed to gain access to class enrollment.
    if request.headers.get("X-User"):
        current_user = int(request.headers.get("X-User"))

        roles_string = request.headers.get("X-Roles")
        current_roles = roles_string.split(",")

        r_flag = True
        # Check if the current user's role matches 'registrar'
        for role in current_roles:
            if role == "registrar":
                r_flag = False

        # Check if the current user's id matches the requested instructor_id
        if r_flag:
            if current_user != instructor_id:
                raise HTTPException(
                    status_code=403, detail="Access forbidden, wrong user"
                )

    # @ Getting the user table resource and using it to retrieve the instructors id and classes
    user = get_table_resource(dynamodb, USER_TABLE)

    instructor_data = enrollment.get_user_item(instructor_id)
    class_data = enrollment.get_class_item(class_id)

    # Following if statements check if both the instructor and class exist
    if not instructor_data or not class_data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Instructor and/or class not found",
        )

    # @ BREIF: getting the instructor id and class id to verify if instructor teaches certain class
    instructor_data = wrapper.run_partiql(
        f"SELECT * FROM {CLASS_TABLE} WHERE instructor_id = ? AND id = ?",
        [instructor_id, class_id],
    )

    # @ BREIF: Checks if the instructor data is not empty as well as the contents inside are not empty
    if "Items" in instructor_data and instructor_data["Items"]:
        # Grabbing the first item in the list
        retrieved_instructor_id = instructor_data["Items"][0].get("instructor_id")
        # verifies that the instructor id matches the one provided
        if retrieved_instructor_id == instructor_id:
            print("Instructor assigned to the class.")
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Instructor not assigned to this class",
            )
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Class not found or instructor not assigned to this class",
        )

    # Getting list of enrolled students using partql
    enrolled_students = wrapper.run_partiql(
        f"SELECT enrolled FROM {CLASS_TABLE} WHERE id = ?", [class_id]
    )

    if "Items" in enrolled_students and enrolled_students["Items"]:
        enrolled_data = enrolled_students["Items"][0].get("enrolled", [])

        enrolled_list = []
        for student_id in enrolled_data:
            user_item = user.get_item(Key={"id": student_id})
            if user_item and "Item" in user_item:
                enrolled_list.append({
                    "id": student_id,
                    "name": user_item["Item"].get("name", "Unknown Name")
                })
        return {"Enrolled": enrolled_list}
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Class has no enrolled students",
        )


# view students who have dropped the class
@router.get("/instructors/{instructor_id}/classes/{class_id}/drop", tags=["Instructor"])
def get_instructor_dropped(instructor_id: int, class_id: int, request: Request):

    # User Authentication
    if request.headers.get("X-User"):
        current_user = int(request.headers.get("X-User"))

        roles_string = request.headers.get("X-Roles")
        current_roles = roles_string.split(",")

        r_flag = True
        # Check if the current user's role matches 'registrar'
        for role in current_roles:
            if role == "registrar":
                r_flag = False

        # Check if the current user's id matches the requested instructor_id
        if r_flag:
            if current_user != instructor_id:
                raise HTTPException(
                    status_code=403, detail="Access forbidden, wrong user"
                )

    # Getting the instructor id
    user = get_table_resource(dynamodb, USER_TABLE)

    instructor_data = enrollment.get_user_item(instructor_id)
    class_data = enrollment.get_class_item(class_id)

    # checking if the instructor and class exists
    if not instructor_data or not class_data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Instructor and/or class not found",
        )

    # getting the instructor id and class id
    instructor_data = wrapper.run_partiql(
        f"SELECT * FROM {CLASS_TABLE} WHERE instructor_id = ? AND id = ?",
        [instructor_id, class_id],
    )

    # checking if the instructor is assigned to class
    if "Items" in instructor_data and instructor_data["Items"]:
        retrieved_instructor_id = instructor_data["Items"][0].get("instructor_id")
        if retrieved_instructor_id == instructor_id:
            print("Instructor assigned to the class.")
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Instructor not assigned to this class",
            )
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Class not found or instructor not assigned to this class",
        )

    # getting list of dropped students
    dropped_students = wrapper.run_partiql(
        f"SELECT dropped FROM {CLASS_TABLE} WHERE id = ?", [class_id]
    )

    if "Items" in dropped_students and dropped_students["Items"]:
        dropped_data = dropped_students["Items"][0].get("dropped", [])

        dropped_list = [
            {
                "id": student_id,
                "name": user.get_item(Key={"id": student_id}).get("Item")["name"],
            }
            for student_id in dropped_data
        ]
        return {"Dropped": dropped_list}
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Class has no dropped students",
        )


# Instructor administratively drop students
@router.post("/instructors/{instructor_id}/classes/{class_id}/students/{student_id}/drop",tags=["Instructor"])
def instructor_drop_class(instructor_id: int, class_id: int, student_id: int, request: Request):

    # User Authentication
    if request.headers.get("X-User"):
        current_user = int(request.headers.get("X-User"))

        roles_string = request.headers.get("X-Roles")
        current_roles = roles_string.split(",")

        r_flag = True
        # Check if the current user's role matches 'registrar'
        for role in current_roles:
            if role == "registrar":
                r_flag = False

        # Check if the current user's id matches the requested instructor_id
        if r_flag:
            if current_user != instructor_id:
                raise HTTPException(
                    status_code=403, detail="Access forbidden, wrong user"
                )

    instructor_data = enrollment.get_user_item(instructor_id)
    student_data = enrollment.get_user_item(student_id)
    class_data = enrollment.get_class_item(class_id)

    # checks if both student and instructor exist in db
    if not instructor_data or not student_data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Instructor and/or student not found",
        )

    # getting the enrolled and dropped list of student ids in class table db
    class_data = wrapper.run_partiql(
        f"SELECT enrolled, dropped FROM {CLASS_TABLE} WHERE id = ?", [class_id]
    )

    # getting the first enrolled and dropped ids in the list
    enrolled_data = class_data.get("Items", [])[0].get("enrolled", [])
    dropped_data = class_data.get("Items", [])[0].get("dropped", [])

    # Removes student_id from the enrolled list
    if student_id in enrolled_data:
        enrolled_data.remove(student_id)
        print(f"Student {student_id} removed from enrolled list.")
    else:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Student not enrolled in this class",
        )

    # DynamoDB updated with the modified enrolled and dropped lists
    try:
        class_table = get_table_resource(dynamodb, CLASS_TABLE)
        class_table.update_item(
            Key={"id": class_id},
            UpdateExpression="SET enrolled = :enrolled, dropped = :dropped",
            ExpressionAttributeValues={
                ":enrolled": enrolled_data,
                ":dropped": dropped_data + [student_id],
            },
        )
        print(f"Student {student_id} added to dropped list.")
    except Exception as e:
        print(f"Error updating lists: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error updating lists",
        )

    return {"Message": "Student successfully dropped"}


# ==========================================registrar==================================================
# Create a new class
@router.post("/registrar/classes/", tags=["Registrar"])
def create_class(class_data: Class):

    existing_class = enrollment.get_class_item(class_data.id)

    if existing_class:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Class with ID {class_data.id} already exists",
        )

    try:
        
        enrollment.add_class(class_data)
        return {"Message": f"Class with ID {class_data.id} created successfully"}

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"type": type(e).__name__, "msg": str(e)},
        )


# Remove a class
@router.delete("/registrar/classes/{class_id}", tags=["Registrar"])
def remove_class(class_id: int):

    # fetch the class data 
    class_data = enrollment.get_class_item(class_id)

    # check if the class exists in the database
    if not class_data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Class not found"
        )
    
    enrollment.delete_class_item(class_id)

    return {"message": "Class removed successfully"}


# Change the assigned instructor for a class
@router.put("/registrar/classes/{class_id}/instructors/{instructor_id}", tags=["Registrar"])
def change_instructor(class_id: int, instructor_id: int):
    # fetch class data
    class_data = enrollment.get_class_item(class_id)

    # check if the class exists in the database
    if not class_data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Class not found"
        )

    # fetch instructor data
    instructor_data = enrollment.get_user_item(instructor_id)

    # check if the instructor exists in the data
    if not instructor_data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Instructor not found"
        )

    # check if instructor is already assigned to the class
    if class_data["instructor_id"] == instructor_data["id"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Instructor already assigned to class"
        )
    
    # fetch the enrollment table from the database
    # update the instructor to the new class 
    class_table = get_table_resource(dynamodb, CLASS_TABLE)
    class_table.update_item(
        Key={
            'id': class_id
        },
        UpdateExpression='SET instructor_id = :instructor_id',
        ExpressionAttributeValues={':instructor_id': instructor_id}
    )

    return {"message": "Instructor changed successfully"}


# Freeze enrollment for classes
@router.put("/registrar/automatic-enrollment/freeze", tags=["Registrar"])
def freeze_automatic_enrollment():
    global FREEZE
    if FREEZE:
        FREEZE = False
        return {"message": "Automatic enrollment unfrozen successfully"}
    else:
        FREEZE = True
        return {"message": "Automatic enrollment frozen successfully"}


# Create a new user (used by the user service to duplicate user info)
@router.post("/registrar/create_user", tags=["Registrar"])
def create_user(user: Create_User):

    if DEBUG:
        print("username: ", user.name)
        print("roles: ", user.roles)

    user_table = get_table_resource(dynamodb,USER_TABLE)
    response_id = user_table.scan(
        Select='COUNT',
        FilterExpression= Key('id').gte(0)
    )

    # incrementing highest + 1 for new id creation
    new_id = response_id.get('Count', 0)+ 1

    user_data = {
        'id': new_id,
        'name':user.name,
        'roles':user.roles
    }

    enrollment.add_user(user_data)

    return {"Message": f'user created successfully. {user.name} Assigned id = {new_id}'}



# ==========================================Test Endpoints==================================================

# None of the following endpoints are required (I assume), but might be helpful
# for testing purposes

# Gets currently enrolled classes for a student
@router.get("/debug/students/{student_id}/enrolled", tags=["Debug"])
def view_enrolled_classes(student_id: int):

    # Check if the student exists in the database
    student_data = enrollment.get_user_item(student_id)

    if not student_data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Student not found"
        )

    # Check if the student is enrolled in any classes
    class_table = get_table_resource(dynamodb, CLASS_TABLE)
    response = class_table.scan(
        FilterExpression='contains(enrolled, :student_id)',
        ExpressionAttributeValues={':student_id': student_id}
    )
    enrolled_data = response.get('Items', [])

    if not enrolled_data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Student not enrolled in any classes",
        )

    # Create a list to store the Class instances
    enrolled_instances = []

    # Iterate through the query results and create Class instances
    for item in enrolled_data:
        # get instructor information
        instructor_data = enrollment.get_user_item(item["instructor_id"])
        # Get waitlist information
        if item["current_enroll"] > item["max_enroll"]:
            current_enroll = item["max_enroll"]
            waitlist = item["current_enroll"] - item["max_enroll"]
        else:
            current_enroll = item["current_enroll"]
            waitlist = 0
        # Create the class instance
        enrolled_instance = Class_Enroll(
            id=item["id"],
            name=item["name"],
            course_code=item["course_code"],
            section_number=item["section_number"],
            current_enroll=current_enroll,
            max_enroll=item["max_enroll"],
            department=item["department"],
            instructor=Instructor(
                id=item["instructor_id"], name=instructor_data["name"]
            ),
            current_waitlist=waitlist,
            max_waitlist=15,
        )
        enrolled_instances.append(enrolled_instance)

    return {"Enrolled": enrolled_instances}


# Get all classes with active waiting lists
@router.get("/debug/waitlist/classes", tags=["Debug"])
def view_all_class_waitlists():

    # fetch all relevant waitlist information
    waitlist_data = wl.get_all_class_waitlists()

    # Check if exist
    if not waitlist_data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="No classes have waitlists"
        )

    # Create a list to store the Waitlist_Info instances
    waitlist_list = []

    # Iterate through the waitlist results and create Waitlist_Info instances
    class_ids = waitlist_data.keys()
    class_ids_list = list(class_ids)
    for cid in class_ids_list:
        temp = []
        class_waitlist = wl.get_class_waitlist(cid)
        student_ids = class_waitlist.keys()
        student_ids_list = list(student_ids)
        for sid in student_ids_list:
            student_data = enrollment.get_user_item(int(sid))
            wl_inst = Waitlist_Instructor(
                student=Student(
                    id=student_data["id"],
                    name=student_data["name"]
                ),
                waitlist_position=class_waitlist[sid]
            )
            temp.append(wl_inst)
        class_instance = Waitlist_Info(
            class_id=int(cid),
            students=temp
        )
        waitlist_list.append(class_instance)

    return {"Waitlists": waitlist_list}


# Search for specific users based on optional parameters,
# if no parameters are given, returns all users
@router.get("/debug/search", tags=["Debug"])
def search_for_users(id: Optional[int] = None, name: Optional[str] = None, role: Optional[str] = None):
    
    table = get_table_resource(dynamodb, USER_TABLE)

    # Construct the query based on the provided parameters
    key_condition_expression = None
    filter_expression = None

    if id is not None:
        key_condition_expression = Key('id').eq(id)
    elif name is not None:
        filter_expression = Attr('name').eq(name)
    elif role is not None:
        filter_expression = Attr('roles').contains(role)

    # Perform the query
    if key_condition_expression is not None:
        response = table.query(
            IndexName='id-index',
            KeyConditionExpression=key_condition_expression
        )
    elif filter_expression is not None:
        response = table.scan(
            IndexName='id-index',
            FilterExpression=filter_expression
        )
    else:
        # If no parameters provided, return all users
        response = table.scan(IndexName='id-index')

    user_data = response.get('Items', [])
    return {"Users": user_data}


# List all classes
@router.get("/debug/classes", tags=["Debug"])
def list_all_classes():

    table = get_table_resource(dynamodb, CLASS_TABLE)
    response = table.scan(IndexName='id-index')

    class_data = response.get('Items', [])
    return {"Users": class_data}
