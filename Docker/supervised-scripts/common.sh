#!/bin/bash

log () {
  echo "${BASENAME} - ${1}"
}

function runcmd() {
  num_procs=$1; shift
  ppn=$1; shift
  cmd_output_dir="$1"; shift
  executable="$1"; shift

  if [ "$MPI_TYPE" = "openmpi" ]; then
	  ppn_arg="-N";
	  hostfile_arg="-hostfile ${HOST_FILE_PATH}"
  else
	  ppn_arg="-ppn"
	  hostfile_arg="-f ${HOST_FILE_PATH}"
  fi
  args="-n $num_procs $ppn_arg $ppn -wdir $cmd_output_dir $hostfile_arg "
  if [ "$MPI_TYPE" = "openmpi" ]; then
    args="${args} --prefix $MPI_INSTALL_PATH"
  fi
  # Intel MPI/MPICH forward all environment variables by default,
  # Open MPI does not.
  if [ "$MPI_TYPE" == "openmpi" ]; then
    env_vars="PATH LD_LIBRARY_PATH"
    if [ -n "$OMP_NUM_THREADS" ]; then
      env_vars="$env_vars OMP_NUM_THREADS"
    fi
    if [ -n "$FI_EFA_ENABLE_SHM_TRANSFER" ]; then
      env_vars="$env_vars FI_EFA_ENABLE_SHM_TRANSFER"
    fi
    for var in $env_vars; do
      args="$args -x $var"
    done
  fi
  addl_mpi_args=${MPI_ARGS:-""}
  if [ "$MPI_TYPE" = "intelmpi" ]; then
    arg="-prepend-rank"
		addl_mpi_args=${addl_mpi_args/-tag-output/$arg}
  fi
  cmd="mpirun $args $addl_mpi_args $executable"
  log "==== starting $cmd : $(date -u) ====" | tee -a "$JOB_LOG_FILE"
  $cmd "$@" 2>&1 | tee -a "$JOB_LOG_FILE"
  return_status=${PIPESTATUS[0]}
  log "return status: $return_status"
  log "==== finished $cmd : $(date -u) ====" | tee -a "$JOB_LOG_FILE"
  return $return_status
}

function generate_tap() {
  test_name="$1"
  return_status="$2"
  tap_count="$3"
  output_file="$4"
  tap_file="$5"

  if [ "$return_status" -eq 0 ]; then
	  echo "ok $tap_count test_name: $test_name, MPI_TYPE: $MPI_TYPE, LIBFABRIC_JOB_TYPE: $LIBFABRIC_JOB_TYPE" >>"$tap_file"
  else
	  echo "not ok $tap_count test_name: $test_name, MPI_TYPE: $MPI_TYPE, LIBFABRIC_JOB_TYPE: $LIBFABRIC_JOB_TYPE" >>"$tap_file"
  fi
  sed 's/^/# /' $output_file  >>"$tap_file"
}