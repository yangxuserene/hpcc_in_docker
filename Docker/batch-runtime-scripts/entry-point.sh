# Copyright 2020 Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

#!/bin/bash
# Launch supervisor
BASENAME="${0##*/}"
log () {
  echo "${BASENAME} - ${1}"
}
AWS_BATCH_EXIT_CODE_FILE="/tmp/batch-exit-code"
supervisord -n -c "/etc/supervisor/supervisord.conf"
sleep 2
# if supervisor dies then read exit code from file we don't want to return the supervisors exit code
log "Upload results to s3"
aws --region us-west-2 s3 cp $HOME/results s3://${S3_BUCKET}/${S3_REPO}/ --recursive
log "Reading exit code from batch script stored at $AWS_BATCH_EXIT_CODE_FILE"
if [ ! -f $AWS_BATCH_EXIT_CODE_FILE ]; then
    echo "Exit code file not found , returning with exit code 1!" >&2
    exit 1
fi
exit $(cat $AWS_BATCH_EXIT_CODE_FILE)
