import logging

from botocore.exceptions import ClientError, WaiterError


# Configure the logger
logger = logging.getLogger(__name__)

table_prefix = "enrollment_"
DEBUG = False

class Enrollment:
    """Encapsulates an Amazon DynamoDB table of enrollment data."""

    def __init__(self, dyn_resource):
        """
        :param dyn_resource: A Boto3 DynamoDB resource.
        """
        self.dyn_resource = dyn_resource
        # The table variable is set during the scenario in the call to
        # 'exists' if the table exists. Otherwise, it is set by 'create_table'.
        if self.check_table_exists("enrollment_class"):
            for table in self.dyn_resource.tables.all():
                if table.name == "enrollment_class":
                    self.classes = table
                else:
                    self.users = table
        else:
            self.classes = None
            self.users = None


    def create_table(self, table_name):
        """
        Creates an Amazon DynamoDB table. The table uses an id for the partition key.

        :param table_name: The name of the table to create.
        :return: The newly created table.
        """
        try:
            if table_name == "class":
                self.classes = self.dyn_resource.create_table(
                    TableName=table_prefix + table_name,
                    KeySchema=[
                        {'AttributeName': 'id', 'KeyType': 'HASH'},  # Partition key
                    ],
                    AttributeDefinitions=[
                        {'AttributeName': 'id', 'AttributeType': 'N'},
                    ],
                    ProvisionedThroughput={
                        "ReadCapacityUnits": 10,
                        "WriteCapacityUnits": 10,
                    },
                )
                self.classes.wait_until_exists()
                self.create_secondary_index(self.classes, 'id-index', 'id')
                table = self.classes
            else:
                self.users = self.dyn_resource.create_table(
                    TableName=table_prefix + table_name,
                    KeySchema=[
                        {'AttributeName': 'id', 'KeyType': 'HASH'},  # Partition key
                    ],
                    AttributeDefinitions=[
                        {'AttributeName': 'id', 'AttributeType': 'N'},
                    ],
                    ProvisionedThroughput={
                        "ReadCapacityUnits": 10,
                        "WriteCapacityUnits": 10,
                    },
                )
                self.users.wait_until_exists()
                self.create_secondary_index(self.users, 'id-index', 'id')
                table = self.users
        except ClientError as err:
            logger.error(
                "Couldn't create table %s. Here's why: %s: %s",
                table_name,
                err.response["Error"]["Code"],
                err.response["Error"]["Message"],
            )
            raise
        else:
            return table
    

    def create_secondary_index(self, table, index_name, attribute_name):
        """
        Creates a global secondary index on the specified table.

        :param table: The DynamoDB table object.
        :param index_name: The name of the index to create.
        :param attribute_name: The attribute to use as the index key.
        """
        try:
            table.update(
                AttributeDefinitions=[
                    {'AttributeName': attribute_name, 'AttributeType': 'N'},
                ],
                GlobalSecondaryIndexUpdates=[
                    {
                        'Create': {
                            'IndexName': index_name,
                            'KeySchema': [
                                {'AttributeName': attribute_name, 'KeyType': 'HASH'},
                            ],
                            'Projection': {
                                'ProjectionType': 'ALL',
                            },
                            'ProvisionedThroughput': {
                                'ReadCapacityUnits': 10,
                                'WriteCapacityUnits': 10,
                            },
                        }
                    },
                ],
            )
            table.wait_until_exists()
        except WaiterError as err:
            logger.error(
                "Couldn't create index %s on table %s. Here's why: %s",
                index_name,
                table.name,
                err,
            )
            raise
    

    def delete_table(self, table_name):
        """
        Deletes an Amazon DynamoDB table.

        :param table_name: The name of the table to delete.
        """
        try:
            table = self.dyn_resource.Table(table_prefix + table_name)
            table.delete()
            table.wait_until_not_exists()
        except ClientError as err:
            logger.error(
                "Couldn't delete table %s. Here's why: %s: %s",
                table_name,
                err.response["Error"]["Code"],
                err.response["Error"]["Message"],
            )
            raise
    

    def add_class(self, class_data):
        """
        Adds a class to the table.

        :param class_data: a class object.
        """
        try:
            self.classes.put_item(Item=dict(class_data))
        except ClientError as err:
            logger.error(
                "Couldn't add class %s to table %s. Here's why: %s: %s",
                class_data.id,
                self.classes.name,
                err.response["Error"]["Code"],
                err.response["Error"]["Message"],
            )
            raise
    

    def add_user(self, user_data):
        """
        Adds a user to the table.

        :param user_data: a user object.
        """
        try:
            self.users.put_item(Item=dict(user_data))
        except ClientError as err:
            logger.error(
                "Couldn't add user %s to table %s. Here's why: %s: %s",
                user_data.id,
                self.users.name,
                err.response["Error"]["Code"],
                err.response["Error"]["Message"],
            )
            raise


    def get_class_item(self, id):
        """
        Gets item data from the table for a specific id.

        :param id: The integer id for the item.
        :return: The data about the requested item.
        """
        try:
            if DEBUG:
                print("id: ", id)
                print("table: ", self.classes)
            response = self.classes.get_item(Key={"id": id})
            # Check if the 'Item' key exists in the response
            if "Item" in response:
                return response["Item"]
            else:
                # If 'Item' key doesn't exist, the item doesn't exist in the table
                return None
        except ClientError as err:
            logger.error(
                "Couldn't get class %s from table %s. Here's why: %s: %s",
                id,
                self.classes.name,
                err.response["Error"]["Code"],
                err.response["Error"]["Message"],
            )
            raise
    

    def get_user_item(self, id):
        """
        Gets item data from the table for a specific id.

        :param id: The integer id for the item.
        :return: The data about the requested item.
        """
        try:
            if DEBUG:
                print("id: ", id)
                print("table: ", self.users)
            response = self.users.get_item(Key={"id": id})
            # Check if the 'Item' key exists in the response
            if "Item" in response:
                return response["Item"]
            else:
                # If 'Item' key doesn't exist, the item doesn't exist in the table
                return None
        except ClientError as err:
            logger.error(
                "Couldn't get user %s from table %s. Here's why: %s: %s",
                id,
                self.users.name,
                err.response["Error"]["Code"],
                err.response["Error"]["Message"],
            )
            raise
    

    def delete_class_item(self, id):
        """
        Deletes a class from the class table.

        :param id: The id of the class to be deleted.
        """
        try:
            self.classes.delete_item(Key={"id": id})
        except ClientError as err:
            logger.error(
                "Couldn't delete class %s. Here's why: %s: %s",
                id,
                err.response["Error"]["Code"],
                err.response["Error"]["Message"],
            )
            raise
    
    
    def delete_user_item(self, id):
        """
        Deletes a user from the user table.

        :param id: The id of the user to be deleted.
        """
        try:
            self.users.delete_item(Key={"id": id})
        except ClientError as err:
            logger.error(
                "Couldn't delete user %s. Here's why: %s: %s",
                id,
                err.response["Error"]["Code"],
                err.response["Error"]["Message"],
            )
            raise
    

    def check_table_exists(self, table_name):
        """
        Check if a table exist in the database.

        :param table_name: name of the table that is being checked
        :return: Either true or false.
        """
        dynamodb_client = self.dyn_resource.meta.client
        try:
            dynamodb_client.describe_table(TableName=table_name)
            if DEBUG:
                print(f"Table {table_name} exists in DynamoDB.")
            return True
        except dynamodb_client.exceptions.ResourceNotFoundException:
            if DEBUG:
                print(f"Table {table_name} does not exist in DynamoDB.")
            return False


class PartiQL:
    """
    Encapsulates a DynamoDB resource to run PartiQL statements.
    """

    def __init__(self, dyn_resource):
        """
        :param dyn_resource: A Boto3 DynamoDB resource.
        """
        self.dyn_resource = dyn_resource


    def run_partiql(self, statement, params):
        """
        Runs a PartiQL statement. A Boto3 resource is used even though
        `execute_statement` is called on the underlying `client` object because the
        resource transforms input and output from plain old Python objects (POPOs) to
        the DynamoDB format. If you create the client directly, you must do these
        transforms yourself.

        :param statement: The PartiQL statement.
        :param params: The list of PartiQL parameters. These are applied to the
                       statement in the order they are listed.
        :return: The items returned from the statement, if any.
        """
        try:
            output = self.dyn_resource.meta.client.execute_statement(
                Statement=statement, Parameters=params
            )
        except ClientError as err:
            if err.response["Error"]["Code"] == "ResourceNotFoundException":
                logger.error(
                    "Couldn't execute PartiQL '%s' because the table does not exist.",
                    statement,
                )
            else:
                logger.error(
                    "Couldn't execute PartiQL '%s'. Here's why: %s: %s",
                    statement,
                    err.response["Error"]["Code"],
                    err.response["Error"]["Message"],
                )
            raise
        else:
            return output
    
    def run_partiql_statement(self, statement):
        """
        Runs a PartiQL statement. A Boto3 resource is used even though
        `execute_statement` is called on the underlying `client` object because the
        resource transforms input and output from plain old Python objects (POPOs) to
        the DynamoDB format. If you create the client directly, you must do these
        transforms yourself.

        :param statement: The PartiQL statement.
        :return: The items returned from the statement, if any.
        """
        try:
            output = self.dyn_resource.meta.client.execute_statement(
                Statement=statement
            )
        except ClientError as err:
            if err.response["Error"]["Code"] == "ResourceNotFoundException":
                logger.error(
                    "Couldn't execute PartiQL '%s' because the table does not exist.",
                    statement,
                )
            else:
                logger.error(
                    "Couldn't execute PartiQL '%s'. Here's why: %s: %s",
                    statement,
                    err.response["Error"]["Code"],
                    err.response["Error"]["Message"],
                )
            raise
        else:
            return output