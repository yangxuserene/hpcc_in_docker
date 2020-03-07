#!/bin/bash
# Copyright 2020 Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

echo "################################"
echo "### Starting Batch Run Script ###"
echo "################################"

BASENAME="${0##*/}"
export output_dir="$HOME/results"; mkdir -p "$output_dir"
export HOST_FILE_PATH="/tmp/hostfile"
export AWS_BATCH_EXIT_CODE_FILE="/tmp/batch-exit-code"
export TEST_LIST=( hpcg )
. /supervised-scripts/common.sh

usage () {
  if [ "${#@}" -ne 0 ]; then
    log "* ${*}"
    log
  fi
  cat <<ENDUSAGE
Usage:
export AWS_BATCH_JOB_NODE_INDEX=0
export AWS_BATCH_JOB_NUM_NODES=10
export AWS_BATCH_JOB_MAIN_NODE_INDEX=0
export AWS_BATCH_JOB_ID=string
./run.sh
ENDUSAGE

  error_exit
}

# Standard function to print an error and exit with a failing return code
error_exit () {
  log "${BASENAME} - ${1}" >&2
  log "${2:-1}" > $AWS_BATCH_EXIT_CODE_FILE
  kill  $(cat /tmp/supervisord.pid)
}



# Check what environment variables are set
if [ -z "${AWS_BATCH_JOB_NODE_INDEX}" ]; then
  usage "AWS_BATCH_JOB_NODE_INDEX not set, unable to determine rank"
fi

if [ -z "${AWS_BATCH_JOB_NUM_NODES}" ]; then
  usage "AWS_BATCH_JOB_NUM_NODES not set. Don't know how many nodes in this job."
fi

if [ -z "${AWS_BATCH_JOB_MAIN_NODE_INDEX}" ]; then
  usage "AWS_BATCH_MULTI_MAIN_NODE_RANK must be set to determine the master node rank"
fi

NODE_TYPE="child"
if [ "${AWS_BATCH_JOB_MAIN_NODE_INDEX}" == "${AWS_BATCH_JOB_NODE_INDEX}" ]; then
  log "Running synchronize as the main node"
  NODE_TYPE="main"
fi

# Check that necessary programs are available
# which aws >/dev/null 2>&1 || error_exit "Unable to find AWS CLI executable."
log "set the libfabric path"
if [ "$LIBFABRIC_JOB_TYPE" = "aws-efa-installer-dev-latest" ]; then
    LIBFABRIC_INSTALL_PATH="/opt/amazon/efa/"
    LIBFABRIC_LIB_PATH="/opt/amazon/efa/lib64/"
else 
    LIBFABRIC_INSTALL_PATH="$HOME/libfabric/install/"
    LIBFABRIC_LIB_PATH="$HOME/libfabric/install/lib/"
fi
export PATH=${LIBFABRIC_INSTALL_PATH}/bin:$PATH
export PATH=${FABTESTS_INSTALL_PATH}/bin/:$PATH 
export PATH=${MPI_INSTALL_PATH}/bin/:$PATH 
export BIN_PATH=${FABTESTS_INSTALL_PATH}/bin/
export LD_LIBRARY_PATH=${LIBFABRIC_LIB_PATH}:${LD_LIBRARY_PATH}
export FI_EFA_ENABLE_SHM_TRANSFER=0

echo "export PATH=${LIBFABRIC_INSTALL_PATH}/bin/:\$PATH" >> $HOME/.bashrc
echo "export PATH=${FABTESTS_INSTALL_PATH}/bin/:\$PATH" >> $HOME/.bashrc
echo "export PATH=${MPI_INSTALL_PATH}/bin/:\$PATH" >> $HOME/.bashrc
echo "export BIN_PATH=${FABTESTS_INSTALL_PATH}/bin/" >> $HOME/.bashrc
echo "export LD_LIBRARY_PATH=${LIBFABRIC_LIB_PATH}:\${LD_LIBRARY_PATH}" >> $HOME/.bashrc

echo "export PATH=${LIBFABRIC_INSTALL_PATH}/bin/:\$PATH" >> $HOME/.bash_profile
echo "export PATH=${FABTESTS_INSTALL_PATH}/bin/:\$PATH" >> $HOME/.bash_profile
echo "export PATH=${MPI_INSTALL_PATH}/bin/:\$PATH" >> $HOME/.bash_profile
echo "export BIN_PATH=${FABTESTS_INSTALL_PATH}/bin/" >> $HOME/.bash_profile
echo "export LD_LIBRARY_PATH=${LIBFABRIC_LIB_PATH}:\${LD_LIBRARY_PATH}" >> $HOME/.bash_profile

if [ "${MPI_TYPE}" = "intelmpi" ]; then
   export I_MPI_DEBUG=1
   export I_MPI_OFI_LIBRARY_INTERNAL=0
   . ${MPI_INSTALL_PATH}/bin/mpivars.sh -ofi_internal=0
   export LD_LIBRARY_PATH=${LIBFABRIC_LIB_PATH}:$LD_LIBRARY_PATH
   export I_MPI_SHM=no # batch container shm size is only 64M
fi
cpus=$(grep -c ^processor /proc/cpuinfo)
threads_per_core=$(lscpu | grep '^Thread(s) per core:' | awk '{ print $4 }')
export TOTAL_THREADS=$(( $cpus / $threads_per_core ))

# wait for all nodes to report
wait_for_nodes () {
  log "Running as master node"

  touch $HOST_FILE_PATH
  ip=$(/sbin/ip -o -4 addr list eth0 | awk '{print $4}' | cut -d/ -f1)
  availablecores=$(nproc)
  log "master details -> $ip:$availablecores"
  echo "$ip" >> $HOST_FILE_PATH

  lines=$(wc -l $HOST_FILE_PATH | awk '{ print $1 }')
  while [ "$AWS_BATCH_JOB_NUM_NODES" -gt "$lines" ]
  do
    log "$lines out of $AWS_BATCH_JOB_NUM_NODES nodes joined, will check again in 1 second"
    sleep 1
    lines=$(wc -l $HOST_FILE_PATH | awk '{ print $1 }' )
  done
  # Make the temporary file executable and run it with any given arguments
  log "All nodes successfully joined"
  cat $HOST_FILE_PATH
  log "executing main MPIRUN workflow, MPI_TYPE: ${MPI_TYPE}"
  cd $output_dir
  for test in "${TEST_LIST[@]}"; do
    bash /supervised-scripts/run_${test}.sh
  done
  log "done! goodbye, writing exit code to $AWS_BATCH_EXIT_CODE_FILE and shutting down my supervisord"
  echo "0" > $AWS_BATCH_EXIT_CODE_FILE
  kill  $(cat /tmp/supervisord.pid)
  exit 0
}


# Fetch and run a script
report_to_master () {
  # looking for masters nodes ip address calling the batch API
  # get own ip and num cpus
  #
  ip=$(/sbin/ip -o -4 addr list eth0 | awk '{print $4}' | cut -d/ -f1)
  log "I am a child node -> $ip, reporting to the master node -> ${AWS_BATCH_JOB_MAIN_NODE_PRIVATE_IPV4_ADDRESS}"
  until echo "$ip" | ssh ${AWS_BATCH_JOB_MAIN_NODE_PRIVATE_IPV4_ADDRESS} "cat >> /$HOST_FILE_PATH"
  do
    echo "Sleeping 5 seconds and trying again"
  done
  log "done! goodbye"  
  exit 0
  }


# Main - dispatch user request to appropriate function
log $NODE_TYPE
case $NODE_TYPE in
  main)
    wait_for_nodes "${@}"
    ;;

  child)
    report_to_master "${@}"
    ;;

  *)
    log $NODE_TYPE
    usage "Could not determine node type. Expected (main/child)"
    ;;
esac
