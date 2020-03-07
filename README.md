# Run HPC apps on AWS Batch Mnp jobs

This repository contains the python scripts to deploy a test framework with AWS Batch Service.

- `runner.py` is the main runner, to deploy the test, run the command
 ```
python runner.py --mode normal --aws_region <aws_region> \ 
                               --batch_az <batch_az> \
                               --batch_node_number <batch_node_number>
```
- To clean the existing resources, 
```
python runner.py --mode clean --aws_region <aws_region>
```         
- `BatchTest.py` contains the helper functions in the batch tests.
- `test_conf.py` contains the configurations of batch tests.
- `userdata` is the original commands in `UserData` section of ec2 launch template. It download and install EFA, such that all instances being launched with this userdata would have EFA equiped. 
- `batch.yaml` is the cloudformation template of the stack that creates VPC, subnet, security groups, and related IAM roles.
- `Docker/` repository contains all the files related to container images, including the `Dockerfile` and the run-time scripts in Batch environment.

The Dockerfile installs the following libs and apps:
1. Install both Open MPI and Intel MPI. 
2. Install HPCG benchmark.
3. Install other necessary packages and libs
This Dockerfile will be used to build the image, which will be pushed to ECR for registering Batch MNP job definition. 

This is an "one-click" test. The runner.py will do the following things:
1. Create all Batch related resources
2. Build the docker image and push it ECR
3. Submit two jobs in sequentail to run the HPCG benchmark. First job will run HPCG with Open MPI, second run with Intel MPI
4. Clean up the created resources once both jobs succeeded, and fetch the test results from S3 to local. 

