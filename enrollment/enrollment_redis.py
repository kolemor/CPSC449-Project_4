import redis

# Connect to Redis
r = redis.Redis(db=1)

# Key patterns
class_waitlist_key = "class:{}:waitlist"
student_waitlists_key = "student:{}:waitlists"
class_waitlist_key_pattern = "class:*:waitlist"
student_waitlists_key_pattern = "student:*:waitlists"

class Waitlist:

    def add_waitlists(class_id, student_id):
        """
        Adds waitlist information to redis.

        :param class_id: The integer id of a class.
        :param student_id: The integer id of a student.
        """
        # Fetch the current highest placement in the class waitlist
        current_highest_placement = r.zrevrange(class_waitlist_key.format(class_id), 0, 0, withscores=True)

        if current_highest_placement:
            # If the waitlist is not empty, increment the placement for the new student
            new_placement = int(current_highest_placement[0][1]) + 1
        else:
            # If the waitlist is empty, start from placement 1
            new_placement = 1

        # Add student to class waitlist with the new placement
        r.zadd(class_waitlist_key.format(class_id), {student_id: new_placement})

        # Add class to student's waitlist with the new placement
        r.zadd(student_waitlists_key.format(student_id), {class_id: new_placement})


    def remove_student_from_waitlists(student_id, class_id):
        """
        Removes a student from a class's waitlist.
        This will also reorder the placement values of the remaining students.

        :param class_id: The integer id of a class.
        :param student_id: The integer id of a student.
        """
        # Get the placement of the student in the class waitlist
        student_placement = r.zscore(class_waitlist_key.format(class_id), student_id)

        if student_placement is not None:
            # Remove the student from the class waitlist
            r.zrem(class_waitlist_key.format(class_id), student_id)

            # Remove the class from the student's waitlists
            r.zrem(student_waitlists_key.format(student_id), class_id)

            # Update the placement values for remaining students
            remaining_students = r.zrangebyscore(class_waitlist_key.format(class_id), student_placement + 1, '+inf', withscores=True)
            for other_student_id, other_placement in remaining_students:
                r.zadd(class_waitlist_key.format(class_id), {other_student_id: other_placement - 1})
                r.zadd(student_waitlists_key.format(student_id), {other_student_id: other_placement - 1})


    def is_student_on_waitlist(student_id, class_id):
        """
        Checks whether a student is on a class's waitlist.
        Returns true or false depending on the result.

        :param class_id: The integer id of a class.
        :param student_id: The integer id of a student.
        :return: Boolean based on if it exists or not.
        """

        # Check if the student is in the class waitlist
        return r.zrank(class_waitlist_key.format(class_id), student_id) is not None


    def get_all_class_waitlists():
        """
        Used mainly for debug purposes.
        Prints all class waitlist information for all classes that have waitlists.
        """
        keys = r.keys(class_waitlist_key_pattern)
        class_waitlists = {}
        for key in keys:
            class_id = key.decode().split(":")[1]
            waitlist = r.zrange(key, 0, -1, withscores=True)
            class_waitlists[class_id] = waitlist
        return class_waitlists


    def get_all_student_waitlists():
        """
        Used mainly for debug purposes. 
        Prints all student waitlist information for all students that are on waitlists.
        """
        keys = r.keys(student_waitlists_key_pattern)
        student_waitlists = {}
        for key in keys:
            student_id = key.decode().split(":")[1]
            waitlists = r.zrange(key, 0, -1, withscores=True)
            student_waitlists[student_id] = waitlists
        return student_waitlists


    def get_waitlist_count(student_id):
        """
        Returns an integer value of how many waitlists a student is currently on.

        :param student_id: The integer id of a student.
        :return: The waitlist counter for the student.
        """
        waitlists = r.zcard(student_waitlists_key.format(student_id))
        return waitlists

   
    def get_class_waitlist(class_id):
        """
        Returns a dictionary of all students on the classes waitlist.

        :param class_id: The integer id of a class.
        :return: A dictionary of all waitlists the student is on, using the format: {class_id: placement}.
        """
        # Get the waitlist information for the student
        waitlist_info_bytes = r.zrange(class_waitlist_key.format(class_id), 0, -1, withscores=True)

        # Convert bytes to string and then to integer for placement values
        waitlist_info = {
            student_id.decode('utf-8'): int(placement) if placement.is_integer() else float(placement)
            for student_id, placement in waitlist_info_bytes
        }

        return waitlist_info
    

    def get_student_waitlist(student_id):
        """
        Returns a dictionary of all waitlists the student is on.

        :param student_id: The integer id of a student.
        :return: A dictionary of all waitlists the student is on, using the format: {class_id: placement}.
        """
        # Get the waitlist information for the student
        waitlist_info_bytes = r.zrange(student_waitlists_key.format(student_id), 0, -1, withscores=True)

        # Convert bytes to string and then to integer for placement values
        waitlist_info = {
            class_id.decode('utf-8'): int(placement) if placement.is_integer() else float(placement)
            for class_id, placement in waitlist_info_bytes
        }

        return waitlist_info