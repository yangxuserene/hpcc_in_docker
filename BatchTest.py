import boto3
import base64
import logging
import time
import docker
import subprocess
import os
from shutil import copy
from test_conf import BATCH_CONFS, DOCKER_CONFS


class BatchTest:
    def __init__(self, region):
        self.region = region
        self.ec2 = boto3.client("ec2", region_name=self.region)
        self.ssm = boto3.client("ssm", region_name=self.region)
        self.batch = boto3.client("batch", region_name=self.region)
        self.ecr = boto3.client("ecr", region_name=self.region)
        self.s3 = boto3.client("s3", region_name=self.region)
        sts = boto3.client("sts", region_name=self.region)
        self.account_id = sts.get_caller_identity()["Account"]
        self.cfn = boto3.client("cloudformation", region_name=self.region)
        self.cfn_r = boto3.resource("cloudformation", region_name=self.region)
        self.logger = logging.getLogger()
        logging.basicConfig(format="%(asctime)s - %(levelname)s - %(module)s - %(message)s", level=logging.INFO)
        self.maximum_query_time = 200

    def create_stack(self, stack_name, template, parameters):
        """
        Create a stack that outputs vpc, subnet, related iam roles and security group
        :param parameters: Dict, cfn template input parameters
        :param template: String, cfn template body
        :param stack_name: String
        :return:
        """
        self.cfn.create_stack(
            StackName=stack_name,
            Parameters=parameters,
            TemplateBody=template,
            Capabilities=['CAPABILITY_NAMED_IAM']
        )
        cfn_waiter = self.cfn.get_waiter('stack_create_complete')
        cfn_waiter.wait(StackName=stack_name, WaiterConfig={
                                            'Delay': 30,
                                            'MaxAttempts': 120})
        cfn_response = self.describe_stack(stack_name)
        if cfn_response['Stacks'][0]['StackStatus'] != 'CREATE_COMPLETE':
            raise RuntimeError("Cloudformation stack: {} failed to be created".format(stack_name))

    def get_stack_output(self, stack_name):
        """
        Generate a dictionary for stack output
        :param stack_name: String
        :return:
        """
        stack = self.cfn_r.Stack(name=stack_name)
        output_dict = {}
        for output in stack.outputs:
            key = output['OutputKey']
            value = output['OutputValue']
            output_dict[key] = value
        return output_dict

    def describe_stack(self, stack_name):
        return self.cfn.describe_stacks(StackName=stack_name)

    def stack_exists(self, stack_name):
        try:
            self.describe_stack(stack_name)
            return True
        except Exception as e:
            self.logger.info("Cloudformation stack: {} does not exist".format(stack_name))
            return False

    def delete_stack(self, stack_name):
        self.cfn.delete_stack(StackName=stack_name)
        cfn_waiter = self.cfn.get_waiter('stack_delete_complete')
        cfn_waiter.wait(StackName=stack_name)

    def create_placement_group(self, placement_group_name):
        return self.ec2.create_placement_group(
            GroupName=placement_group_name,
            Strategy='cluster'
        )

    def placement_group_exists(self, placement_group_name):
        try:
            response = self.ec2.describe_placement_groups(GroupNames=[placement_group_name, ])
            return True
        except Exception as e:
            logging.info("placement group with name: {} does not exist".format(placement_group_name))
            return False

    def delete_placement_group(self, placement_group_name, max_trial=5, wait_time=60):
        """
        wrapper of ec2.delete_placement_group
        :param placement_group_name: String
        :param max_trial: Integer, maximum number of deletion trials, default 5
        :param wait_time: Integer, period of deletion request, default 60 (sec)
        :return:
        """
        for i in range(max_trial):
            try:
                self.ec2.delete_placement_group(GroupName=placement_group_name)
                return
            except Exception as e:
                self.logger.warning("An error occurred when deleting the \
                placement_group, wait {} secs for next try ".format(wait_time))
                time.sleep(wait_time)
        self.logger.warning("Number of deletion trials exceeds MAX_TRIAL: {}".format(max_trial))

    def create_key_pair(self, key_name, key_pair_file):
        response = self.ec2.create_key_pair(KeyName=key_name)
        key_material = response['KeyMaterial']
        with open(key_pair_file, "w") as f:
            f.write(key_material)
        os.chmod(key_pair_file, 400)

    def key_pair_exists(self, key_name):
        try:
            response = self.ec2.describe_key_pairs(KeyNames=[key_name, ])
            return True
        except Exception as e:
            logging.info("key pair with name: {} does not exist".format(key_name))
            return False

    def delete_key_pair(self, key_name):
        return self.ec2.delete_key_pair(KeyName=key_name)

    def get_ami(self):
        ami_path = "/aws/service/ecs/optimized-ami/amazon-linux/recommended/image_id"
        response = self.ssm.get_parameters(Names=[ami_path, ])
        ami_id = response.get('Parameters')[0]['Value']
        return ami_id

    def create_launch_template(self, launch_template_name, key_name, ecs_instance_profile, subnet_id, security_group,
                               placement_group, instance_type="c5n.18xlarge"):
        """
        :param key_name: String, ec2 key pair name
        :param ecs_instance_profile: String, arn of ecs instance profile
        :param launch_template_name: String, launch template name
        :param subnet_id: String, should be a private subnet with NAT gateway
        :param security_group: String, efa enabled security group
        :param placement_group: String, the name of placement group
        :param instance_type: String, default c5n.18xlarge
        :return:
        """
        ami_id = self.get_ami()
        userdata = open("userdata", "r").read()
        encode = base64.b64encode(userdata.encode('utf-8'))
        userdata_b64 = encode.decode("utf-8")

        launch_template = {"LaunchTemplateName": launch_template_name}
        launch_template_data = {"InstanceType": instance_type, "ImageId": ami_id,
                                "IamInstanceProfile": {"Arn": ecs_instance_profile}, "KeyName": key_name}

        network_interface = {"DeviceIndex": 0, "Groups": [security_group], "SubnetId": subnet_id,
                             "InterfaceType": "efa",
                             "Description": "NetworkInterfaces Configuration For EFA and Batch"}
        launch_template_data["NetworkInterfaces"] = [network_interface, ]

        launch_template_data["Placement"] = {"GroupName": placement_group}
        tags = [{"Key": "Name", "Value": "EFA enabled Batch"},
                {"Key": "from-lt", "Value": "networkInterfacesConfig-EFA-Batch"}]
        launch_template_data["TagSpecifications"] = [{"ResourceType": "instance", "Tags": tags}, ]
        launch_template_data["UserData"] = userdata_b64
        launch_template["LaunchTemplateData"] = launch_template_data

        response = self.ec2.create_launch_template(LaunchTemplateName=launch_template_name,
                                                   LaunchTemplateData=launch_template_data)
        return response

    def launch_template_exists(self, launch_template_name):
        """
        :param launch_template_name: String
        :return:
        """

        try:
            response = self.ec2.describe_launch_templates(LaunchTemplateNames=[launch_template_name, ])
            return True
        except Exception as e:
            logging.info("launch template with name: {} does not exist".format(launch_template_name))
            return False

    def delete_launch_template(self, launch_template_name):
        """
        :param launch_template_name: String
        :return:
        """
        return self.ec2.delete_launch_template(LaunchTemplateName=launch_template_name)

    def create_batch_compute_environment(self, compute_environment_name, batch_service_role, subnet_id,
                                         ecs_instance_profile, placement_group, launch_template_name,
                                         min_vcpus=0, max_vcpus=576, desired_vcpus=0,
                                         instance_type="c5n.18xlarge"):
        """
        :param compute_environment_name: String
        :param batch_service_role: String
        :param subnet_id: String
        :param ecs_instance_profile: String
        :param placement_group: String
        :param launch_template_name:
        :param min_vcpus: Integer
        :param max_vcpus: Integer
        :param desired_vcpus: Integer
        :param instance_type: String
        :return:
        """
        response = self.batch.create_compute_environment(
            computeEnvironmentName=compute_environment_name,
            type='MANAGED',
            state='ENABLED',
            computeResources={
                'type': 'EC2',
                'minvCpus': min_vcpus,
                'maxvCpus': max_vcpus,
                'desiredvCpus': desired_vcpus,
                'instanceTypes': [
                    instance_type,
                ],
                'subnets': [
                    subnet_id,
                ],
                'instanceRole': ecs_instance_profile,
                'placementGroup': placement_group,
                'launchTemplate': {
                    'launchTemplateName': launch_template_name,
                }
            },
            serviceRole=batch_service_role
        )
        response_ = self.describe_compute_environment(compute_environment_name)
        query_time = 0
        while True:
            response_ = self.describe_compute_environment(compute_environment_name)
            query_time = query_time + 1
            if response_['computeEnvironments'][0]['status'] == 'VALID':
                break
            else:
                time.sleep(10)
            if query_time == self.maximum_query_time:
                raise RuntimeError(" Maximum query time reached")
        return response

    def describe_compute_environment(self, compute_environment_name):
        return self.batch.describe_compute_environments(computeEnvironments=[compute_environment_name, ])

    def compute_environment_exists(self, compute_environment_name):
        """
        :param: compute_environment_name: String
        :return:
        """
        response = self.describe_compute_environment(compute_environment_name)
        return len(response['computeEnvironments']) > 0

    def delete_compute_environment(self, compute_environment_name):
        self.batch.update_compute_environment(computeEnvironment=compute_environment_name,
                                              state='DISABLED')
        query_time = 0
        while True:
            response = self.describe_compute_environment(compute_environment_name)
            query_time = query_time + 1
            if response['computeEnvironments'][0]['status'] == 'VALID':
                break
            else:
                time.sleep(10)
            if query_time == self.maximum_query_time:
                raise RuntimeError(" Maximum query time reached")

        self.batch.delete_compute_environment(computeEnvironment=compute_environment_name)
        query_time = 0
        while True:
            if query_time == self.maximum_query_time:
                raise RuntimeError(" Maximum query time reached")
            if self.compute_environment_exists(compute_environment_name):
                query_time = query_time + 1
                time.sleep(10)
            else:
                break

    def create_job_queue(self, job_queue_name, computer_environment_name, compute_environment_order=1, priority=10):
        """

        :param job_queue_name:
        :param computer_environment_name:
        :param compute_environment_order:
        :param priority:
        :return:
        """
        response = self.batch.create_job_queue(
            jobQueueName=job_queue_name,
            state='ENABLED',
            priority=priority,
            computeEnvironmentOrder=[
                {
                    'order': compute_environment_order,
                    'computeEnvironment': computer_environment_name
                },
            ]
        )
        query_time = 0
        while True:
            if query_time == self.maximum_query_time:
                raise RuntimeError(" Maximum query time reached")
            response_ = self.describe_job_queue(job_queue_name)
            query_time = query_time + 1
            if response_['jobQueues'][0]['status'] == 'VALID':
                break
            else:
                time.sleep(10)
        return response

    def describe_job_queue(self, job_queue_name):
        return self.batch.describe_job_queues(jobQueues=[job_queue_name, ])

    def job_queue_exists(self, job_queue_name):
        """
        :param: job_queue_name: String
        :return:
        """
        response = self.describe_job_queue(job_queue_name)
        return len(response['jobQueues']) > 0

    def delete_job_queue(self, job_queue_name):
        self.batch.update_job_queue(jobQueue=job_queue_name, state='DISABLED')
        query_time = 0
        while True:
            response = self.describe_job_queue(job_queue_name)
            query_time = query_time + 1
            if response['jobQueues'][0]['status'] == 'VALID':
                break
            else:
                time.sleep(10)
            if query_time == self.maximum_query_time:
                raise RuntimeError(" Maximum query time reached")

        self.batch.delete_job_queue(jobQueue=job_queue_name)
        query_time = 0
        while True:
            if self.job_queue_exists(job_queue_name):
                query_time = query_time + 1
                time.sleep(10)
            else:
                break
            if query_time == self.maximum_query_time:
                raise RuntimeError(" Maximum query time reached")

    def register_job_definition(self, job_definition_name, container_image, batch_job_role, num_nodes,
                                container_user="efauser", vcpus=72, memory=184320):
        """

        :param job_definition_name: String
        :param container_image: String, URI of ECS container image
        :param batch_job_role: String, arn of batch job role
        :param container_user: String, default: "efauser"
        :param num_nodes: Integer, number of nodes in batch job
        :param vcpus: Integer, number of vcpus in each node
        :param memory: Integer, memory of each node.
        :return:
        """
        node_properties = {"numNodes": num_nodes, "mainNode": 0}
        node_range_properties = {"targetNodes": "0:"}
        container = {"user": container_user, "image": container_image, "jobRoleArn": batch_job_role, "vcpus": vcpus,
                     "memory": memory, "linuxParameters": {"devices": [{"hostPath": "/dev/infiniband/uverbs0"}]},
                     "ulimits": [{"hardLimit": -1, "name": "memlock", "softLimit": -1}]}
        node_range_properties["container"] = container
        node_range_properties = [node_range_properties]
        node_properties["nodeRangeProperties"] = node_range_properties

        response = self.batch.register_job_definition(jobDefinitionName=job_definition_name,
                                                      type='multinode',
                                                      nodeProperties=node_properties)
        return response

    def describe_job_definition(self, job_definition_name):
        """
        wrapper of batch.describe_job_definition()
        :param job_definition_name: String
        :return:
        """
        return self.batch.describe_job_definitions(jobDefinitionName=job_definition_name)

    def job_definition_exists(self, job_definition_name):
        """

        :param job_definition_name:
        :return: Boolean
        """
        response = self.describe_job_definition(job_definition_name)
        return len(response['jobDefinitions']) > 0

    def deregister_job_definition(self, job_definition_arn):
        """
        wrapper of batch.deregister_job_definition
        :param job_definition_arn: String
        :return:
        """
        return self.batch.deregister_job_definition(
            jobDefinition=job_definition_arn
        )

    def submit_job(self, job_name, job_queue, job_definition):
        """
        wrapper of batch.submit_job()
        :param job_name:
        :param job_queue:
        :param job_definition:
        :return:
        """
        response = self.batch.submit_job(jobName=job_name,
                                         jobQueue=job_queue,
                                         jobDefinition=job_definition)
        return response

    def describe_job(self, job_id):
        """
        Wrapper of batch.describe_jobs
        :param job_id: String
        :return:
        """
        return self.batch.describe_jobs(jobs=[job_id, ])

    def wait_until_all_jobs_finish(self, job_ids, query_job_status_period=300, query_job_status_maximum_time=48):
        """
        Waiter for all jobs finish
        :param query_job_status_maximum_time: the maximum times of query for job status
        :param job_ids: List of job_id Strings
        :param query_job_status_period: Integer, default: 300
        :return:
        """
        query_time = 0
        while True:
            is_running = False
            for job_id in job_ids:
                response = self.describe_job(job_id)
                job_status = response['jobs'][0]['status']
                job_name = response['jobs'][0]['jobName']
                self.logger.info("job_id: {}, job_name: {}, job_status: {}".format(
                    job_id, job_name, job_status
                ))
                is_running = (is_running or (job_status != "SUCCEEDED" and job_status != "FAILED"))
            query_time = query_time + 1
            if not is_running:
                break
            else:
                if query_time == query_job_status_maximum_time:
                    raise RuntimeError(" Maximum query time reached")
                self.logger.info("Wait {} secs for next query".format(query_job_status_period))
                time.sleep(query_job_status_period)

    def terminate_job(self, job_id, reason="abort"):
        """

        :param job_id:
        :param reason:
        :return:
        """
        response = self.batch.terminate_job(jobId=job_id, reason=reason)
        return response

    def create_repository(self, repository_name):
        """
        wrapper of ecr.create_repository
        :param repository_name: String
        :return: client response
        """
        return self.ecr.create_repository(repositoryName=repository_name)

    def describe_repository(self, repository_name):
        """
        wrapper of ecr.describe_repositories
        :param repository_name: ecr repository name
        :return:
        """
        return self.ecr.describe_repositories(repositoryNames=[repository_name, ])

    def delete_repository(self, repository_name):
        """
        wrapper of ecr.delete_repository
        :param repository_name: String
        :return:
        """
        return self.ecr.delete_repository(repositoryName=repository_name, force=True)

    def repository_exists(self, repository_name):
        """
        check if given ecr repository exists
        :param repository_name: String
        :return: Boolean
        """
        try:
            response = self.describe_repository(repository_name)
            return True
        except Exception as e:
            self.logger.info("ecr repository with name: {} does not exist".format(repository_name))
            return False

    def create_container_image(self, build_args, local_tag):
        """
        Create docker image and push to ECR
        :param build_args: Dict, image build args, keys: MPI_TYPE, MPI_INSTALL_PATH, LIBFABRIC_JOB_TYPE
        :param local_tag: String, "Docker image tag"
        :return: ECR uri of container image
        """
        docker_client = docker.from_env()
        self.logger.info("delete unused images to free space")
        cmd = "docker system prune -af"
        subprocess.check_call(cmd, shell=True)
        self.logger.info("Build docker image {} with args: {}".format(local_tag, build_args))
        docker_client.images.build(path=os.path.join(os.getcwd(), "Docker/"), nocache=True,
                                   tag=local_tag, buildargs=build_args)

        self.logger.info("Tag image in registry")
        ecr_repository = "aws-batch-{}".format(local_tag)
        ecr_uri = "{}.dkr.ecr.{}.amazonaws.com".format(self.account_id, self.region)
        cmd = "docker tag {}:latest {}/{}".format(local_tag, ecr_uri, ecr_repository)
        subprocess.check_call(cmd, shell=True)

        self.logger.info("Login to ECR")
        cmd = "aws ecr get-login --no-include-email --region {}".format(self.region)
        out = subprocess.check_output(cmd, shell=True)
        subprocess.check_call(out, shell=True)

        if not self.repository_exists(ecr_repository):
            self.logger.info("Create ECR repository: {}".format(ecr_repository))
            self.create_repository(ecr_repository)
        container_image_uri = ecr_uri + "/" + ecr_repository + ":latest"
        self.logger.info("Push image to ECR {}".format(container_image_uri))
        docker_client.images.push(container_image_uri)
        self.logger.info("Image is ready in ECR. Next, create batch job definition.")
        return container_image_uri

    def bucket_exists(self, bucket_name):
        response = self.s3.list_buckets()
        buckets_list = [bucket['Name'] for bucket in response['Buckets']]
        if bucket_name in buckets_list:
            return True
        else:
            return False

    def create_bucket(self, bucket_name):
        """
        create s3 bucket
        :param bucket_name:
        :return:
        """
        cmd = "aws s3 --region {} mb s3://{}".format(self.region, bucket_name)
        subprocess.check_call(cmd, shell=True)

    def s3_upload_file(self, local_path, bucket_name, remote_path):
        cmd = "aws --region {} s3 cp {} s3://{}/{}".format(self.region, local_path,
                                                           bucket_name, remote_path)
        subprocess.check_call(cmd, shell=True)

    def s3_download_file(self, bucket_name, remote_path, local_path):
        cmd = "aws --region {} s3 cp s3://{}/{} {}".format(self.region, bucket_name,
                                                           remote_path, local_path)
        subprocess.check_call(cmd, shell=True)

    def s3_upload_dir(self, local_path, bucket_name, remote_path):
        """
        upload a directory to s3, use aws cli for convenience
        :param local_path:
        :param bucket_name:
        :param remote_path:
        :return:
        """
        cmd = "aws --region {} s3 cp {} s3://{}/{} --recursive".format(self.region, local_path,
                                                                       bucket_name, remote_path)
        subprocess.check_call(cmd, shell=True)

    def s3_download_dir(self, bucket_name, remote_path, local_path):
        """
        download a directory from s3, use aws cli for convenience
        :param bucket_name:
        :param remote_path:
        :param local_path:
        :return:
        """
        cmd = "aws --region {} s3 cp s3://{}/{} {} --recursive".format(self.region, bucket_name,
                                                                       remote_path, local_path)
        subprocess.check_call(cmd, shell=True)

    def clean_up(self):
        """
        Clean up batch job environment.
        :return:
        """
        placement_group_name = BATCH_CONFS["placement_group_name"]
        key_name = BATCH_CONFS["key_name"]
        launch_template_name = BATCH_CONFS["launch_template_name"]
        ce_name = BATCH_CONFS["compute_environment_name"]
        job_queue_name = BATCH_CONFS["job_queue_name"]
        job_definition_names = BATCH_CONFS["job_definition_names"].values()
        image_tags = [image["local_tag"] for image in DOCKER_CONFS.values()]
        batch_stack_name = BATCH_CONFS["batch_stack_name"]

        for job_definition_name in job_definition_names:
            if self.job_definition_exists(job_definition_name):
                jd_response = self.describe_job_definition(job_definition_name)
                for jd in jd_response["jobDefinitions"]:
                    jd_arn = jd["jobDefinitionArn"]
                    self.logger.info("deregister job definition: {}".format(jd_arn))
                    self.deregister_job_definition(jd_arn)

        for image_tag in image_tags:
            ecr_repository = "aws-batch-{}".format(image_tag)
            if self.repository_exists(ecr_repository):
                self.logger.info("delete ecr repository: {}".format(ecr_repository))
                self.delete_repository(ecr_repository)

        if self.job_queue_exists(job_queue_name):
            self.logger.info("delete job queue: {}".format(job_queue_name))
            self.delete_job_queue(job_queue_name)

        if self.compute_environment_exists(ce_name):
            self.logger.info("delete compute environment: {}".format(ce_name))
            self.delete_compute_environment(ce_name)

        if self.launch_template_exists(launch_template_name):
            self.logger.info("delete launch template: {}".format(launch_template_name))
            self.delete_launch_template(launch_template_name)

        if self.placement_group_exists(placement_group_name):
            self.logger.info("delete placement group: {}".format(placement_group_name))
            self.delete_placement_group(placement_group_name)

        if self.key_pair_exists(key_name):
            self.logger.info("delete ec2 key-pair: {}".format(key_name))
            self.delete_key_pair(key_name)

        if self.stack_exists(batch_stack_name):
            self.logger.info("delete cloudformation stack: {}".format(batch_stack_name))
            self.delete_stack(batch_stack_name)
