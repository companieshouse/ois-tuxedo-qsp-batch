# ois-tuxedo-qsp-transfer

An AWS Lambda function for collating and transferring QSP batch data from CloudWatch to a remote FTP server for further processing.

This project forms part of the [ois-tuxedo-stack](https://github.com/companieshouse/ois-tuxedo-stack) set of services and infrastructure. It replaces a set of cron jobs that were previously used and functions by collating batch data generated from multiple sources before transferring the resulting data file to a remove FTP server.

During normal operation, the `ORDERS` service in [ois-tuxedo](https://github.com/companieshouse/ois-tuxedo) writes comma-separated batch data to a local log file whose path is specified in the `QSPFILE` environment variable (typically set in configuration files in [ois-tuxedo-configs](https://github.com/companieshouse/ois-tuxedo-configs)). Many `ORDERS` services may be active in the same _environment_—distributed across one or more EC2 instances—and log data for those services will be exported via CloudWatch agent to the same log group, one log stream per EC2 instance. The Lambda function filters data in the log group for a given time period—taking all log streams into consideration—and collates the resulting data before transfer to a remote FTP server.

## Configuration

The following Lambda function environment variables are required:

| Name |  |
|--|--|
| `DATA_FILE_PREFIX` | A filename prefix for the data file that will be transferred to the remote FTP server. A date _suffix_ will be automatically added to the filename using the format `%d-%m-%Y`. |
| `FTP_HOST` | The hostname or IP address of the remote FTP server to which data will be transferred. |
| `FTP_PATH` | The directory path on the remote FTP server to which data will be transferred. |
| `LOG_GROUP_NAME` | The CloudWatch log group name from which data will be sourced. All log streams for this log group will be considered when processing data, dependent upon the presence of data in those log streams for the time period being processed. |
| `SECRET_NAME` | The [ARN](https://docs.aws.amazon.com/general/latest/gr/aws-arns-and-namespaces.html) or name of the secret to retrieve from [AWS Secrets Manager](https://aws.amazon.com/secrets-manager/). The secret is expected to contain two key/value pairs, named `username` and `password`, with valid credentials for the remove FTP server to which data will be transferred. |
