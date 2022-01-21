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
from botocore.exceptions import ClientError

logger = logging.getLogger()
logger.setLevel(logging.INFO)

def get_ftp_credentials():
    try:
        client = boto3.client('secretsmanager')
        get_secret_value_response = client.get_secret_value(SecretId=os.environ['SECRET_NAME'])
    except Exception as e:
        raise e
    else:
        if 'SecretString' in get_secret_value_response:
            secret = get_secret_value_response['SecretString']
        else:
            secret = base64.b64decode(get_secret_value_response['SecretBinary'])

        return json.loads(secret)

def create_data_file(date):
    if not re.match(r"\d{2}-\d{2}-\d{4}", date):
        raise Exception(f"Date parameter value '{date}' does not match expected format DD-MM-YYYY")

    log_group = os.environ['LOG_GROUP_NAME']
    start_time = int(time.mktime(time.strptime(f"{date} 00:00:00", '%d-%m-%Y %H:%M:%S'))) * 1000
    end_time = int(time.mktime(time.strptime(f"{date} 23:59:59", '%d-%m-%Y %H:%M:%S'))) * 1000

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

    events = events + response['events']

    while 'nextToken' in response.keys():
        token = response['nextToken']
        response = client.filter_log_events(
            logGroupName = log_group,
            startTime = start_time,
            endTime = end_time,
            nextToken = token
        )

        events = events + response['events']

    date_suffix = datetime.strptime(date, '%d-%m-%Y').strftime('%d%m%Y')
    file_path = f"/tmp/{os.environ['DATA_FILE_PREFIX']}.{date_suffix}"

    with open(file_path, 'w') as file:
        for event in events:
            file.write(event['message'] + '\n')

    return file_path

def transfer_data_file(path):
    filename = os.path.basename(path)
    credentials = get_ftp_credentials()

    with FTP(os.environ['FTP_HOST']) as ftp, open(path, 'rb') as file:
        ftp.login(credentials['username'], credentials['password'])
        ftp.cwd('upload')
        logging.info(f"Transferring file: {filename}")
        response = ftp.storbinary(f"STOR {filename}", fp=file)


def lambda_handler(event, context):

    try:
        logger.info(f'Event: {event}')

        if 'date' in event:
            date = event['date']
            logging.info(f"Using date provided in parameter: '{date}'")
        else:
            date = datetime.strftime(datetime.now() - timedelta(days=1), '%d-%m-%Y')
            logging.info(f"Using yesterday's date: '{date}'")

        transfer_data_file(create_data_file(date))

        logging.info("QSP transfer completed")

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
