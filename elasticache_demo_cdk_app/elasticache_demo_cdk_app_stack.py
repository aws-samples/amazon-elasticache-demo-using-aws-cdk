from aws_cdk import (
    # Duration,
    Stack,
    aws_rds as rds,
    aws_ec2 as ec2,
    aws_iam as iam,
    aws_elasticache as elasticache,
    RemovalPolicy,
    CfnOutput
)

from constructs import Construct

# Load user data for the Web Server EC2 instance
with open("./elasticache_demo_cdk_app/user_data.sh") as f:
    user_data = f.read()

app_port = 8008

class ElasticacheDemoCdkAppStack(Stack):

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # VPC        
        vpc = ec2.Vpc(self, "VPC",
            nat_gateways=1,
            cidr="10.0.0.0/16",
            subnet_configuration=[
                ec2.SubnetConfiguration(name="public",subnet_type=ec2.SubnetType.PUBLIC,cidr_mask=24),
                ec2.SubnetConfiguration(name="private",subnet_type=ec2.SubnetType.PRIVATE_WITH_NAT,cidr_mask=24)
            ]
        )


        # Security Groups
        db_sec_group = ec2.SecurityGroup(
            self, "db-sec-group",security_group_name="db-sec-group", vpc=vpc, allow_all_outbound=True,
        )
        webserver_sec_group = ec2.SecurityGroup(
            self, "webserver_sec_group",security_group_name="webserver_sec_group", vpc=vpc, allow_all_outbound=True,
        )
        redis_sec_group = ec2.SecurityGroup(
            self, "redis-sec-group",security_group_name="redis-sec-group", vpc=vpc, allow_all_outbound=True,
        )   

        private_subnets_ids = [ps.subnet_id for ps in vpc.private_subnets]

        redis_subnet_group = elasticache.CfnSubnetGroup(
            scope=self,
            id="redis_subnet_group",
            subnet_ids=private_subnets_ids,  # todo: add list of subnet ids here
            description="subnet group for redis"
        )

        # Add ingress rules to security group
        webserver_sec_group.add_ingress_rule( 
            peer=ec2.Peer.ipv4("0.0.0.0/0"),
            description="Flask Application",
            connection=ec2.Port.tcp(app_port),
        )

        db_sec_group.add_ingress_rule( 
            peer=webserver_sec_group,
            description="Allow MySQL connection",
            connection=ec2.Port.tcp(3306),
        )

        redis_sec_group.add_ingress_rule(
            peer=webserver_sec_group,
            description="Allow Redis connection",
            connection=ec2.Port.tcp(6379),            
        )

        # RDS MySQL Database
        rds_instance = rds.DatabaseInstance(
            self, id='RDS-MySQL-Demo-DB',
            database_name='covid',
            engine=rds.DatabaseInstanceEngine.mysql(
                version=rds.MysqlEngineVersion.VER_8_0_28
            ),
            vpc=vpc,
            port=3306,
            instance_type= ec2.InstanceType.of(
                ec2.InstanceClass.BURSTABLE3,
                ec2.InstanceSize.MEDIUM,
            ),
            removal_policy=RemovalPolicy.DESTROY,
            deletion_protection=False,
            iam_authentication=True,
            security_groups=[db_sec_group],
            storage_encrypted=True,
            vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PRIVATE_WITH_NAT)
        )

        # Elasticache for Redis cluster
        redis_cluster = elasticache.CfnCacheCluster(
            scope=self,
            id="redis_cluster",
            engine="redis",
            cache_node_type="cache.t3.small",
            num_cache_nodes=1,
            cache_subnet_group_name=redis_subnet_group.ref,
            vpc_security_group_ids=[redis_sec_group.security_group_id],
        )  

        # AMI definition
        amzn_linux = ec2.MachineImage.latest_amazon_linux(
            generation=ec2.AmazonLinuxGeneration.AMAZON_LINUX_2,
            edition=ec2.AmazonLinuxEdition.STANDARD,
            virtualization=ec2.AmazonLinuxVirt.HVM,
            storage=ec2.AmazonLinuxStorage.GENERAL_PURPOSE
            )

        # Instance Role and SSM Managed Policy
        role = iam.Role(self, "ElasticacheDemoInstancePolicy", assumed_by=iam.ServicePrincipal("ec2.amazonaws.com"))
        role.add_managed_policy(iam.ManagedPolicy.from_aws_managed_policy_name("AmazonSSMManagedInstanceCore")) 
        role.add_managed_policy(iam.ManagedPolicy.from_aws_managed_policy_name("AWSCloudFormationReadOnlyAccess")) 
 
        # The following inline policy makes sure we allow only retrieving the secret value, provided the secret is already known. 
        # It does not allow listing of all secrets.
        role.attach_inline_policy(iam.Policy(self, "secret-read-only",  
            statements=[iam.PolicyStatement(
                actions=["secretsmanager:GetSecretValue"],
                resources=["arn:aws:secretsmanager:*"],
                effect=iam.Effect.ALLOW
            )]
        ))  

        # EC2 Instance for Web Server
        instance = ec2.Instance(self, "WebServer",
            instance_type=ec2.InstanceType("t3.small"),
            machine_image=amzn_linux,
            vpc = vpc,
            role = role,
            vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PUBLIC),
            security_group=webserver_sec_group,
            user_data=ec2.UserData.custom(user_data)
            )   

        # Generate CloudFormation Outputs
        CfnOutput(scope=self,id="secret_name",value=rds_instance.secret.secret_name)
        CfnOutput(scope=self,id="mysql_endpoint",value=rds_instance.db_instance_endpoint_address)
        CfnOutput(scope=self,id="redis_endpoint",value=redis_cluster.attr_redis_endpoint_address)
        CfnOutput(scope=self,id="webserver_public_ip",value=instance.instance_public_ip)
        CfnOutput(scope=self,id="webserver_public_url",value=instance.instance_public_dns_name)
