import os
import sys
import traceback
import json
import boto3
import base64
import time
import re
import logging

from ftplib import FTP
from datetime import datetime, timedelta

logger = logging.getLogger()
logger.setLevel(logging.INFO)

def check_environment_variables() -> None:
    required_vars = [
        'DATA_FILE_PREFIX',
        'FTP_HOST',
        'LOG_GROUP_NAME',
        'SECRET_NAME',
    ]

    missing_vars = []
    for env_var in required_vars:
        if os.getenv(env_var) is None:
            missing_vars.append(env_var)

    if len(missing_vars) > 0:
        raise Exception(f"Mandatory environment variable(s) undefined: {', '.join(missing_vars)}")

def get_epoch_time_in_millis(dt: datetime) -> int:
    return int(time.mktime(dt)) * 1000

def get_ftp_credentials() -> str:
    client = boto3.client('secretsmanager')
    get_secret_value_response = client.get_secret_value(SecretId=os.environ['SECRET_NAME'])

    if 'SecretString' in get_secret_value_response:
        secret = get_secret_value_response['SecretString']
    else:
        secret = base64.b64decode(get_secret_value_response['SecretBinary'])

    return json.loads(secret)

def create_data_file(date: str) -> str:
    if not re.match(r"\d{2}-\d{2}-\d{4}", date):
        raise Exception(f"Date parameter value '{date}' does not match expected format: DD-MM-YYYY")

    log_group = os.environ['LOG_GROUP_NAME']
    start_time = get_epoch_time_in_millis(time.strptime(f"{date} 00:00:00", '%d-%m-%Y %H:%M:%S'))
    end_time = get_epoch_time_in_millis(time.strptime(f"{date} 23:59:59", '%d-%m-%Y %H:%M:%S'))

    logging.info(f"Using log group name: {log_group}")
    logging.info(f"Using epoch start time in milliseconds: {start_time}")
    logging.info(f"Using epoch end time in milliseconds: {end_time}")

    events = []

    client = boto3.client('logs')
    response = client.filter_log_events(
        logGroupName = log_group,
        startTime = start_time,
        endTime = end_time
    )

    events.extend(response['events'])

    while 'nextToken' in response.keys():
        token = response['nextToken']
        response = client.filter_log_events(
            logGroupName = log_group,
            startTime = start_time,
            endTime = end_time,
            nextToken = token
        )

        events.extend(response['events'])

    if len(events) == 0:
        return '';

    date_suffix = datetime.strptime(date, '%d-%m-%Y').strftime('%d%m%Y')
    file_path = f"/tmp/{os.environ['DATA_FILE_PREFIX']}.{date_suffix}"

    with open(file_path, 'w') as file:
        for event in events:
            file.write(event['message'] + '\n')

    return file_path

def transfer_data_file(path: str) -> None:
    filename = os.path.basename(path)
    credentials = get_ftp_credentials()

    with FTP(os.environ['FTP_HOST']) as ftp, open(path, 'rb') as file:
        ftp.login(credentials['username'], credentials['password'])
        ftp.cwd('upload')
        logging.info(f"Transferring file: {filename}")
        response = ftp.storbinary(f"STOR {filename}", fp=file)

def lambda_handler(event, context):
    try:
        check_environment_variables()

        if 'date' in event:
            date = event['date']
            logging.info(f"Using date provided in parameter: '{date}'")
        else:
            date = datetime.strftime(datetime.now() - timedelta(days=1), '%d-%m-%Y')
            logging.info(f"Using yesterday's date: '{date}'")

        path = create_data_file(date)

        if not path:
            logger.info("No data for given time period; processing complete")
        else:
            transfer_data_file(path)
            logging.info("Data file transfer completed")

        return {
            'statusCode': 200
        }

    except Exception as e:
        exception_type, exception_value, stack_trace = sys.exc_info()
        pretty_stack_trace = traceback.format_exception(exception_type, exception_value, stack_trace)
        error_message = json.dumps({
            "errorType": exception_type.__name__,
            "errorMessage": str(exception_value),
            "stackTrace": pretty_stack_trace
        })
        logger.error(error_message)
