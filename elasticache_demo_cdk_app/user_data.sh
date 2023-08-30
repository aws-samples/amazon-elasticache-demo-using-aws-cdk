#!/usr/bin/sh

yum update -y
yum install mariadb -y
yum install git -y
yum install tree -y
yum install wget -y
yum install jq -y

pip3 install flask redis pymysql boto3 requests
pip3 uninstall urllib3
pip3 install 'urllib3<2.0'

cd /home/ec2-user
git clone https://github.com/aws-samples/amazon-elasticache-demo-using-aws-cdk.git
cd amazon-elasticache-demo-using-aws-cdk
wget https://aws-blogs-artifacts-public.s3.amazonaws.com/artifacts/DBBLOG-1922/sample-dataset.zip
unzip sample-dataset.zip
rm sample-dataset.zip

chown -R ec2-user:ec2-user /home/ec2-user/*

