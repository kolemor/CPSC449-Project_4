#!/bin/bash

# Update package lists
sudo apt update

# Install sqlite3
sudo apt install --yes sqlite3

# Install ruby-foreman
sudo apt install -y ruby-foreman

# Install entr
sudo apt install -y entr

# ***** Block to install KrakenD *****
# Add the GPG key for the specified keyserver
sudo apt-key adv --keyserver keyserver.ubuntu.com --recv 5DE6FD698AD6FDD2

# Add Krakend repository to sources list
sudo echo "deb https://repo.krakend.io/apt stable main" | sudo tee /etc/apt/sources.list.d/krakend.list

# Update package lists
sudo apt update

# Install KrakenD
sudo apt install -y krakend

# ***** Block to install REdis *****
# Update package lists
sudo apt update

# Install REdis 
sudo apt install --yes redis

# ***** Block to install AWS CLI *****
# Download the installer
curl "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o "awscliv2.zip"

# Unzip the installer
unzip awscliv2.zip

# Install AWS CLI
sudo ./aws/install

# Remove the zip file
rm "awscliv2.zip"

# Configure AWS
# Define the Variables
aws_access_key_id="AKIAIOSFODNN7EXAMPLE"
aws_secret_access_key="wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"
aws_default_region="us-west-2"
aws_output_format="json"

# Run aws configure with the provided input
aws configure set aws_access_key_id "$aws_access_key_id"
aws configure set aws_secret_access_key "$aws_secret_access_key"
aws configure set default.region "$aws_default_region"
aws configure set default.output "$aws_output_format"

# ***** Block to install DynamoDB *****
# Update package lists
sudo apt update

# Install JRE
sudo apt install --yes openjdk-19-jre-headless

# Download DynamoDB
curl https://d1ni2b6xgvw0s0.cloudfront.net/v2.x/dynamodb_local_latest.tar.gz -o "dynamodbv2.tar.gz"

# Unzip DynamoDB
tar -xzvf dynamodbv2.tar.gz

# Remove the zip file
rm "dynamodbv2.tar.gz"

# Move extra files to DynamoDB folder
mv LICENSE.txt README.txt THIRD-PARTY-LICENSES.txt DynamoDBLocal_lib/

# *************************************

# Install HTTPie for Terminal to work with REST APIs
sudo apt install -y httpie

# Install pip for Python 3
sudo apt install -y python3-pip

# Install required libaries for the project
pip3 install -r requirements.txt

# Print 'Installation Successful'
echo "\n\n"
echo "*****************************************"
echo "*        Installation Successful        *"
echo "*****************************************"
echo "To start the servers, run: 'sh run.sh'"
echo "To create or restore the databases to default, run: 'sh ./bin/db_creation.sh'"
echo "\n" 