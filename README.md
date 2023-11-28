# Project 3

## create a venv and activate it then install the requirements

`python -m venv myenv`

`source myenv/bin/activate`

`sh ./bin/install.sh`

- NOTE: running the install command will install ALL dependencies and requirements, including aws and DynamoDB, it should also properly configure aws as well

## then in the main directory run this command to run the services

`sh run.sh`

- as a note, when running foreman for the first time, the folder structure for litefs will be created in var.

- once running, then you can create the users.db. It should be created in primary and propagated to secondary and tertiary. If not you may need to restart for it to work properly.

## Create the databases or restore them to their default data

`sh ./bin/db_creation.sh`

### If you want to individually create each database, you can instead run these commands from the main directory

`python enrollment/populate_enrollment.py`

`python users/populate_users.py`

- the user database population can take anywhere from 30 seconds to a couple minutes as there are ~600 users, and each one needs to have their password hashed, which takes some time. I'll see if I can optimize this later on, but for now it works

## Links to test the api

- Enrollment service

  `http://localhost:5000/docs`

  `http://localhost:5001/docs`

  `http://localhost:5002/docs`

- user service

  `http://localhost:5100/docs`

- KrakenD

  `http://localhost:5400/api/`

# Enrollment Service testing variables

- student_id 1 is on 3 waitlists (class_id: 4, 8, 13)
- class_id 1 (with instructor_id 501) has 4 dropped students
- class_id 4, 6, 8, 13, 14 are all full, but have open waitlists
- class_id 12 is fully enrolled, with a full waitlist
- all classes have a default max_enroll value of 30
- there are 500 student_ids, with upwards of 300 of them currently being used
- there are 100 instructor_ids, with only ~14 of them being used

- there are useful debug endpoints that you can use to view information on what is contained within the database

# Users Service testing variables

- the first user has a username of "James Smith"
- Every user's non-hashed password is the same as their username
- Users 1 - 500 have the 'student' role
- Users 501 - 600 have the 'instructor' role
- Users 551 - 600 also have the 'registrar' role

- there are useful debug endpoints that you can use to view information on what is contained within the database

# Overview of files

## Enrollment Service

- enrollment_routes.py:

  contains all the routes and code for the endpoints of the API

- enrollment.db:

  the database file for the enrollment service

- enrollment.py:

  the 'main' file for the enrollment service

- populate_enrollment.py:

  creates and populates the dynamodb and redis databases

- enrollment_schemas.py:

  has all the base models for the service

- enrollment_dynamo.py

  has two classes, one called enrollment which has a bunch of methods used for dynamodb data manipulation,
  with the other called partiQL which has methods used for partiQL querying

- enrollment_redis.py

  has a class called Waitlist which has a bunch of methods used to manipulate data in redis.

## Users Service

- populate_users.py:

  creates and populates the users database

- users_routes.py:

  contains all the routes and code for the endpoints of the API

- users.db:

  the database file for the users service

- users.py:

  the 'main' file for the users service

- users_schemas.py:

  has all the base models for the service

- users_hash.py:

  has functions which handle password hashing

## utils

- mkclaims.py

  prints to the terminal an example of a JWT claim

- mkjwk.py

  prints to the terminal a public / private RSA key pair

- postman.txt

  has useful information you can use to copy past in postman requests to make it easier

## jwk

- private.json

  contains the private keys used in JWT verification

- public.json

  contains the public keys used in JWT verification

## Misc files

- Procfile:

  runs both services

- requirements.txt:

  the required libraries that pip needs to install
