import redis
import boto3

from fastapi import APIRouter, HTTPException
from enrollment.enrollment_dynamo import Enrollment
from enrollment.enrollment_redis import Subscription
from notification.notification_schema import Sub_List

router = APIRouter()

# Connect to Redis
r = redis.Redis(db=2)

# Connect to DynamoDB
dynamodb = boto3.resource("dynamodb", endpoint_url="http://localhost:5500")

# Create class items
enrollment = Enrollment(dynamodb)
sub = Subscription()

# ==========================================endpoints==================================================

# Subscribe to notifications for a new course
@router.post("/students/{student_id}/subscribe/{class_id}", tags=["Notification"])
def subscribe_to_course(student_id: int, class_id: int, email: str = "", webhook_url: str = ""):

    # Check if student and class exist
    # Fetch student data from db
    student_data = enrollment.get_user_item(student_id)

    # Fetch class data from db
    class_data = enrollment.get_class_item(class_id)

    # Check if exist
    if not student_data or not class_data:
        raise HTTPException(
            status_code=404, detail=f"Student_id {student_id} or class_id {class_id} not found"
        )
    
    # Check if the student already has a subscription for the class
    if sub.is_student_subscribed(student_id, class_id):
        raise HTTPException(status_code=400, detail=f"Student_id {student_id} already has a subscription for class_id {class_id}.")

    # Check if email or webhook_url is provided
    if not email and not webhook_url:
        raise HTTPException(status_code=400, detail="Provide either an email address or a Webhook callback URL, or both.")

    # Create a subscription payload
    subscription_payload = {
        "email": email,
        "webhook_url": webhook_url,
    }

    # Store subscription in Redis
    sub.add_subscription(student_id, class_id, subscription_payload)
    sub_data = Sub_List(
        class_id=class_id,
        email=subscription_payload["email"],
        webhook_url=subscription_payload["webhook_url"]
    )

    return {"message": "Subscription successful", "subscription": sub_data}


# List all subscriptions for a student
@router.get("/students/{student_id}/subscriptions", tags=["Notification"])
def list_current_subscriptions(student_id: int):

    # check if student exists
    # Fetch student data from db
    student_data = enrollment.get_user_item(student_id)

    if not student_data:
        raise HTTPException(
            status_code=404, detail=f"Student_id {student_id} not found"
        )
    
    # Check if the student has any subscriptions
    if not sub.check_student_subscription(student_id):
        raise HTTPException(status_code=404, detail=f"Student_id {student_id} has no subscriptions.")

    # Retrieve subscriptions from Redis using the correct key pattern
    subscriptions_data = sub.get_all_subscriptions(student_id)

    # Convert subscriptions to instances of Sub_List model
    subscriptions = [
        Sub_List(class_id=sub_data['class_id'], email=sub_data['email'], webhook_url=sub_data['webhook_url'])
        for sub_data in subscriptions_data
    ]

    return {"message": "Current subscriptions", "subscriptions": subscriptions}


# Allow student to unsubscribe from a course
@router.delete("/students/{student_id}unsubscribe/{class_id}", tags=["Notification"])
def unsubscribe_from_course(student_id: int, class_id: int):
    
    # Check if student and class exist
    # Fetch student data from db
    student_data = enrollment.get_user_item(student_id)

    # Fetch class data from db
    class_data = enrollment.get_class_item(class_id)

    # Check if exist
    if not student_data or not class_data:
        raise HTTPException(
            status_code=404, detail=f"Student_id {student_id} or class_id {class_id} not found"
        )
    
    # Check if the student has a subscription for the class
    if not sub.is_student_subscribed(student_id, class_id):
        raise HTTPException(status_code=404, detail=f"Student_id {student_id} is not subscribed to class_id {class_id}.")
    
    sub.delete_subscription(student_id, class_id)
    
    return {"message": f"Successfully unsubscribed student_id {student_id} from class_id {class_id}"}


# ==========================================DEBUG==================================================


# Debug endpoint to wipe redis subscription data
@router.delete("/debug/wipe", tags=["Debug"])
def wipe_redis_data():
    
    r.flushdb()

    return {"message": "Redis Wiped"}
