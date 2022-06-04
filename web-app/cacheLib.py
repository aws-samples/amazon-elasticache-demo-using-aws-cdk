import os
import json
import redis
import pymysql
import boto3
import sys
import os.path
import requests

def store_configs (config_file, configs):
    '''
    This function stores configurations in a json file.
    '''    
    with open(config_file, 'w') as fp:
        json.dump(configs, fp)


def load_configs (config_file):
    '''
    This function loads configurations from a json file.
    '''     
    data = {}
    with open(config_file) as fp:
        data = json.load(fp)
    return data

def get_secret(secret_name,region_name):
    '''
    This function retrieves information from Secrets Manager.
    ''' 

    # Create a Secrets Manager client
    session = boto3.session.Session()
    client = session.client(
        service_name='secretsmanager',
        region_name=region_name
    )

    # In this sample we only handle the specific exceptions for the 'GetSecretValue' API.
    # See https://docs.aws.amazon.com/secretsmanager/latest/apireference/API_GetSecretValue.html
    # We rethrow the exception by default.

    try:
        get_secret_value_response = client.get_secret_value(
            SecretId=secret_name
        )
    except ClientError as e:
        if e.response['Error']['Code'] == 'DecryptionFailureException':
            # Secrets Manager can't decrypt the protected secret text using the provided KMS key.
            # Deal with the exception here, and/or rethrow at your discretion.
            raise e
        elif e.response['Error']['Code'] == 'InternalServiceErrorException':
            # An error occurred on the server side.
            # Deal with the exception here, and/or rethrow at your discretion.
            raise e
        elif e.response['Error']['Code'] == 'InvalidParameterException':
            # You provided an invalid value for a parameter.
            # Deal with the exception here, and/or rethrow at your discretion.
            raise e
        elif e.response['Error']['Code'] == 'InvalidRequestException':
            # You provided a parameter value that is not valid for the current state of the resource.
            # Deal with the exception here, and/or rethrow at your discretion.
            raise e
        elif e.response['Error']['Code'] == 'ResourceNotFoundException':
            # We can't find the resource that you asked for.
            # Deal with the exception here, and/or rethrow at your discretion.
            raise e
    else:
        # Decrypts secret using the associated KMS CMK.
        # Depending on whether the secret is a string or binary, one of these fields will be populated.
        if 'SecretString' in get_secret_value_response:
            secret = json.loads(get_secret_value_response['SecretString'])
        else:
            secret = json.loads(base64.b64decode(get_secret_value_response['SecretBinary']))
    return secret


def get_stack_outputs(stack_name,region_name):
    '''
    This function retrieves all outputs of a stack from CloudFormation.
    '''     
    stack_outputs = {}
    cf_client = boto3.client('cloudformation',region_name=region_name)
    response = cf_client.describe_stacks(StackName=stack_name)
    outputs = response["Stacks"][0]["Outputs"]
    for output in outputs:
        stack_outputs[output["OutputKey"]] = output["OutputValue"]

    response = get_secret(stack_outputs['secretname'],region_name)

    stack_outputs['db_password'] = response['password']
    stack_outputs['db_name'] = response['dbname']
    stack_outputs['db_port'] = response['port']
    stack_outputs['db_username'] = response['username']
    stack_outputs['db_host'] = response['host']

    return stack_outputs


def mysql_execute_command(sql, db_host, db_username, db_password):
    '''
    This function excutes the sql statement, does not return any value.
    '''
    try:
        con = pymysql.connect(host=db_host,
                                user=db_username,
                                password=db_password,
                                autocommit=True,
                                local_infile=1)
        # Create cursor and execute SQL statement
        cursor = con.cursor()
        cursor.execute(sql)
        con.close()
       
    except Exception as e:
        print('Error: {}'.format(str(e)))
        sys.exit(1)


def mysql_fetch_data(sql, db_host, db_username, db_password, db_name):
    '''
    This function excutes the sql query and returns dataset.
    '''
    try:
        con = pymysql.connect(host=db_host,
                                user=db_username,
                                password=db_password,
                                database=db_name,
                                autocommit=True,
                                local_infile=1,
                                charset='utf8mb4',
                                cursorclass=pymysql.cursors.DictCursor)                              
        # Create cursor and execute SQL statement
        cursor = con.cursor()
        cursor.execute(sql)
        data_set = cursor.fetchall()
        con.close()
        return data_set
       
    except Exception as e:
        print('Error: {}'.format(str(e)))
        sys.exit(1)

def flush_cache():
    '''
    This function flushes all records from the cache.
    '''     
    
    Cache.flushall()


def query_mysql_and_cache(sql,db_host, db_username, db_password, db_name):
    '''
    This function retrieves records from the cache if it exists, or else gets it from the MySQL database.
    '''     

    res = Cache.get(sql)

    if res:
        print ('Records in cache...')
        return ({'records_in_cache': True, 'data' : res})
          
    res = mysql_fetch_data(sql, db_host, db_username, db_password, db_name)
    
    if res:
        print ('Cache was empty. Now populating cache...')  
        Cache.setex(sql, ttl, json.dumps(res))
        return ({'records_in_cache': False, 'data' : res})
    else:
        return None


def query_mysql(sql,db_host, db_username, db_password, db_name):
    '''
    This function retrieve records from the database.
    ''' 

    res = mysql_fetch_data(sql, db_host, db_username, db_password, db_name)
    
    if res:
        print ('Records in database...')
        return res
    else:
        return None

def initialize_database(configs):
    '''
    This function initialize the MySQL database if not already done so and generates
    all configurations needed for the application.
    ''' 
   
    # Initialize Database
    print ('Initializing MySQL Database...')

    #Drop table if exists
    sql_command = "DROP TABLE IF EXISTS covid.articles;"
    mysql_execute_command(sql_command, configs['db_host'], configs['db_username'], configs['db_password'])

    #Create table
    sql_command = "CREATE TABLE covid.articles (OBJECTID INT, SHA TEXT, PossiblePlace TEXT, Sentence TEXT, MatchedPlace TEXT, DOI  TEXT, Title TEXT, Abstract TEXT, PublishedDate TEXT, Authors TEXT, Journal TEXT, Source TEXT, License TEXT, PRIMARY KEY (OBJECTID));"
    mysql_execute_command(sql_command, configs['db_host'], configs['db_username'], configs['db_password'])

    #Load CSV file into mysql
    sql_command = """
    LOAD DATA LOCAL INFILE '{0}' 
    INTO TABLE covid.articles 
    FIELDS TERMINATED BY ',' 
    ENCLOSED BY '"'
    LINES TERMINATED BY '\n'
    IGNORE 1 ROWS;
    """.format(configs['dataset_file'])
    mysql_execute_command(sql_command, configs['db_host'], configs['db_username'], configs['db_password'])


# Load configurations from config file
config_file = 'configs.json'

if os.path.exists(config_file):
    configs = load_configs (config_file)
    print('Local config file found...')
else:
    print ('Missing config file...')
    exit

stack_name = configs['stack_name']
ttl = configs['ttl']
app_port = configs['app_port']
max_rows = configs['max_rows'] #max # of rows to query from database
dataset_file = configs['dataset_file']
region_name = requests.get('http://169.254.169.254/latest/dynamic/instance-identity/document').json()['region']
configs['region_name'] = region_name

# If datbase is not populated, retrieve endpoints for the database, cache and compute instance from CloudFormation and populate the database
if configs['database_populated'] is False:

    # Get additional configurations from CloudFormation and save on disk
    stack_outputs = get_stack_outputs(stack_name,region_name)
    for key in stack_outputs.keys():
        configs[key] = stack_outputs[key] 

    # Get all configs. If database was not initialized, it will be populated with sample data.
    initialize_database(configs)
    configs['database_populated'] = True
    store_configs (config_file, configs)

# Initialize the cache
Cache = redis.Redis.from_url('redis://' + configs['redisendpoint'] + ':6379')

db_table = 'articles'
db_tbl_fields = ['OBJECTID', 'Sentence', 'Title', 'Source']
sql_fields = ', '.join(db_tbl_fields)

sql = "select SQL_NO_CACHE " + sql_fields + " from " + db_table  +  " where  Sentence like '%delta%' order by OBJECTID limit " + str(max_rows)
