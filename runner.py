import logging
import os
import subprocess
import argparse
from shutil import copy, rmtree
from BatchTest import BatchTest
from test_conf import DOCKER_CONFS, BATCH_CONFS, S3_BUCKET, S3_REPO_BASENAME

logger = logging.getLogger()
logging.basicConfig(format="%(asctime)s - %(levelname)s - %(module)s - %(message)s", level=logging.INFO)


def _init_argparser():
    parser = argparse.ArgumentParser(
        description="Run Batch Test", formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    parser.add_argument(
        "--mode",
        help="if mode is clean, jump to clean_up section",
        default="normal",
    )
    parser.add_argument(
        "--aws_region",
        help="aws region where test runs",
        default="us-west-2",
    )
    parser.add_argument(
        "--batch_node_number",
        help="node number of batch multi-node job",
        default="2",
    )
    parser.add_argument(
        "--batch_az",
        help="availability zone of Batch job subnet",
        default="us-west-2a",
    )
    return parser


args = _init_argparser().parse_args()

def clean_up():
    """
    Wrapper of BatchTest.clean_up()
    :return:
    """
    batch_test = BatchTest(region=args.aws_region)
    batch_test.clean_up()


def main():
    """Entry-point for tests executor."""
    logger.info("Starting tests with parameters {0}".format(args))
    batch_test = BatchTest(region=args.aws_region)

    placement_group_name = BATCH_CONFS["placement_group_name"]
    key_name = BATCH_CONFS["key_name"]
    key_pair_file = BATCH_CONFS["key_pair_file"]
    launch_template_name = BATCH_CONFS["launch_template_name"]
    ce_name = BATCH_CONFS["compute_environment_name"]
    job_queue_name = BATCH_CONFS["job_queue_name"]
    bucket_name = S3_BUCKET
    batch_stack_name = BATCH_CONFS["batch_stack_name"]

    if not batch_test.stack_exists(batch_stack_name):
        logger.info("Create Cloudformation stack: {}".format(batch_stack_name))
        template = open("batch.yaml", "r").read()
        stack_parameters = [{'ParameterKey': 'BatchAZ',
                             'ParameterValue': args.batch_az}, ]
        batch_test.create_stack(batch_stack_name, template, stack_parameters)

    stack_output = batch_test.get_stack_output(batch_stack_name)
    subnet_id = stack_output['BatchPrivateSubnet']
    security_group = stack_output['BatchSecurityGroup']
    batch_job_role = stack_output['BatchJobRole']
    batch_service_role = stack_output['BatchServiceRole']
    ecs_instance_profile = stack_output['BatchECSInstanceProfile']

    if not batch_test.placement_group_exists(placement_group_name):
        logger.info("Create EC2 Placement Group: {}".format(placement_group_name))
        batch_test.create_placement_group(placement_group_name)

    if not batch_test.key_pair_exists(key_name):
        logger.info("Create EC2 key pair: {}".format(placement_group_name))
        batch_test.create_key_pair(key_name, key_pair_file)

    if not batch_test.launch_template_exists(launch_template_name):
        logger.info("Create EC2 launch template: {}".format(launch_template_name))
        lt_response = batch_test.create_launch_template(launch_template_name, key_name, ecs_instance_profile,
                                                        subnet_id, security_group, placement_group_name)
        lt_id = lt_response['LaunchTemplate']['LaunchTemplateId']

    if not batch_test.compute_environment_exists(ce_name):
        logger.info("Create Batch Compute Environment: {}".format(ce_name))
        ce_response = batch_test.create_batch_compute_environment(ce_name, batch_service_role, subnet_id,
                                                                  ecs_instance_profile, placement_group_name,
                                                                  launch_template_name)

    if not batch_test.job_queue_exists(job_queue_name):
        logger.info("Create Batch Job Queue: {}".format(job_queue_name))
        job_queue_response = batch_test.create_job_queue(job_queue_name=job_queue_name,
                                                         computer_environment_name=ce_name)

    if not batch_test.bucket_exists(bucket_name):
        logger.info("Create S3 Bucket: {}".format(bucket_name))
        batch_test.create_bucket(bucket_name)

    job_definitions = []
    jobs = []
    for conf_key, conf_value in DOCKER_CONFS.items():
        build_args = conf_value["build_args"]
        # override the batch node number in DOCKER_CONFS
        build_args["NUM_NODES"] = args.batch_node_number
        local_tag = conf_value["local_tag"]
        container_image = batch_test.create_container_image(build_args, local_tag)

        job_definition_name = BATCH_CONFS["job_definition_names"][conf_key]
        job_definitions.append(job_definition_name)
        logger.info("Register Batch Job Definition: {}".format(job_definition_name))
        jd_response = batch_test.register_job_definition(job_definition_name=job_definition_name,
                                                         container_image=container_image,
                                                         batch_job_role=batch_job_role,
                                                         num_nodes=int(args.batch_node_number))

        job_name = BATCH_CONFS["job_names"][conf_key]
        logger.info("Submit Job: {}".format(job_name))
        job_response = batch_test.submit_job(job_name=job_name, job_queue=job_queue_name,
                                             job_definition=job_definition_name)
        job_id = job_response['jobId']
        logger.info("Job ID: {}".format(job_id))
        jobs.append(job_id)

    logger.info("Wait until all jobs finish ...")
    batch_test.wait_until_all_jobs_finish(jobs, query_job_status_period=300)

    logger.info("Fetch results from s3 ...")
    os.mkdir(S3_REPO_BASENAME)
    batch_test.s3_download_dir(bucket_name, S3_REPO_BASENAME, S3_REPO_BASENAME)

    logger.info("Postprocessing ...")
    cwd = os.getcwd()
    for conf_key, conf_value in DOCKER_CONFS.items():
        libfabric_job_type = conf_value["build_args"]["LIBFABRIC_JOB_TYPE"]
        mpi_type = conf_value["build_args"]["MPI_TYPE"]
        path = os.path.join(cwd, S3_REPO_BASENAME, conf_key)
        os.chdir(path)
    os.chdir(cwd)

    if os.getenv("JENKINS_HOME") is not None:
        logger.info("Upload jenkins logs and files to s3 ...")
        jenkins_home = os.getenv("JENKINS_HOME")
        jenkins_workspace = os.getenv("WORKSPACE")
        jenkins_job_name = os.getenv("JOB_NAME")
        jenkins_build_number = os.getenv("BUILD_NUMBER")
        batch_test.s3_upload_file(os.path.join(jenkins_home, "jobs", jenkins_job_name,
                                               "builds", jenkins_build_number, "log"),
                                  bucket_name, os.path.join(S3_REPO_BASENAME, "jenkins-log"))
        batch_test.s3_upload_dir(jenkins_workspace, bucket_name, S3_REPO_BASENAME)

    logger.info("Clean up ...")
    batch_test.clean_up()


if __name__ == "__main__":
    if args.mode == "normal":
        main()
    elif args.mode == "clean":
        clean_up()
    else:
        raise ValueError("Unexpected --mode: {}".format(args.mode))
