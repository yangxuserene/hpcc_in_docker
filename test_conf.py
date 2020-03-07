import os
from datetime import datetime
now = datetime.now()
CURRENT_TIME = now.strftime("%Y%D%H%M%S").replace('/', '')
ci_stack_name = os.getenv('stack_name', 'infosphere-apps')
S3_BUCKET = "{}-batch-tests".format(ci_stack_name)
S3_REPO_BASENAME = "batch-log-{}".format(CURRENT_TIME)
JENKINS_BUILD_NUMBER = os.getenv("BUILD_NUMBER", "0")
# Warning: can be overridden by runtime args --batch_node_number
NUM_NODES = "2"
DOCKER_CONFS = {
    "ompi-master": {
        "local_tag": "ompi-master-{}".format(JENKINS_BUILD_NUMBER),
        "build_args": {
            "MPI_TYPE": "openmpi",
            "MPI_INSTALL_PATH": "/opt/amazon/openmpi/",
            "LIBFABRIC_JOB_TYPE": "master",
            "S3_BUCKET": S3_BUCKET,
            "S3_REPO": "{}/ompi-master".format(S3_REPO_BASENAME),
            "NUM_NODES": NUM_NODES,
        }
    },
    "impi-master": {
        "local_tag": "impi-master-{}".format(JENKINS_BUILD_NUMBER),
        "build_args": {
            "MPI_TYPE": "intelmpi",
            "MPI_INSTALL_PATH": "/opt/intel/compilers_and_libraries_2020.0.166/linux/mpi/intel64/",
            "LIBFABRIC_JOB_TYPE": "master",
            "S3_BUCKET": S3_BUCKET,
            "S3_REPO": "{}/impi-master".format(S3_REPO_BASENAME),
            "NUM_NODES": NUM_NODES,
        }
    }
}

BATCH_CONFS = {
    "batch_stack_name": "batch-env-stack-{}".format(JENKINS_BUILD_NUMBER),
    "placement_group_name": "batch-placement-group-{}".format(JENKINS_BUILD_NUMBER),
    "key_name": "batch-key-pair-{}".format(JENKINS_BUILD_NUMBER),
    "key_pair_file": "batch-key-pair-{}.pem".format(JENKINS_BUILD_NUMBER),
    "launch_template_name": "efa-batch-launch-template-{}".format(JENKINS_BUILD_NUMBER),
    "compute_environment_name": "efa-batch-ce-{}".format(JENKINS_BUILD_NUMBER),
    "job_queue_name": "efa-batch-job-queue-{}".format(JENKINS_BUILD_NUMBER),
    "job_definition_names": {
        "ompi-master": "efa-batch-job-ompi-master-definition-{}".format(JENKINS_BUILD_NUMBER),
        "impi-master": "efa-batch-job-impi-master-definition-{}".format(JENKINS_BUILD_NUMBER),
    },
    "job_names": {
        "ompi-master": "efa-batch-job-ompi-master-{}".format(JENKINS_BUILD_NUMBER),
        "impi-master": "efa-batch-job-impi-master-{}".format(JENKINS_BUILD_NUMBER),
    },
}
