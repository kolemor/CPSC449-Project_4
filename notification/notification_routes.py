import redis

from fastapi import APIRouter

router = APIRouter()

# Connect to Redis
r = redis.Redis(db=2)

# ==========================================Endpoints==================================================

# The following endpoints are just placeholders until we actually start coding
# their functionality. Everything is subject to change.

# Allow student to subscribe to notifications for a new course
@router.get("/students/subscribe", tags=["Notification"])
def subscribe_to_course():

    return {"message": "Placeholder message"}


# Allow student to list their current subscriptions
@router.post("/students/subscriptions", tags=["Notification"])
def list_current_subscriptions():

    return {"message": "Placeholder message"}


# Allow student to unsubscribe from a course
@router.put("/students/unsubscribe", tags=["Notification"])
def unsubscribe_from_course():

    return {"message": "Placeholder message"}



