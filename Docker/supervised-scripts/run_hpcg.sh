#!/bin/bash
BASENAME="${0##*/}"
JOB_LOG_FILE="${output_dir}/log-$(date -u +%F-%R).log"
tap_file="${output_dir}/hpcg_${MPI_TYPE}_${LIBFABRIC_JOB_TYPE}.tap"
. /supervised-scripts/common.sh
runtime=300
tap_count=0
export OMP_NUM_THREADS=1
log "Running HPCG on $NUM_NODES nodes with $TOTAL_THREADS ppn"
tap_count=$((tap_count+1))
resdir="${output_dir}/hpcg"
resfile="${resdir}/multi.${NUM_NODES}.${TOTAL_THREADS}"
csvfile="${resdir}/hpcg_result.csv"
mkdir -p "$resdir"
if [ ! -e "$csvfile" ]; then
	echo "Threads,Nodes,GFlop/s,Runtime" >> "$csvfile"
fi
runcmd $((TOTAL_THREADS * NUM_NODES)) $TOTAL_THREADS . /hpcg/build/bin/xhpcg --rt-time $runtime --nx=112 --ny=112 --nz=112 | tee "$resfile"
return_status=${PIPESTATUS[0]}
output_file=$(find "." -name 'HPCG-Benchmark*')
if [ ! -f "$output_file" ]; then
	echo "HPCG-Benchmark file not found." >&2
	return_status=1
fi
pattern='Final Summary::HPCG result is VALID with a GFLOP\/s rating of='
result=$(grep "$pattern" "$output_file" | sed "s/$pattern//")
if [ -n "$result" ]; then
	echo "$TOTAL_THREADS,$NUM_NODES,$result,$runtime" >> "$csvfile"
fi
generate_tap "hpcg" $return_status $tap_count $resfile $tap_file
sed -i "1i 1..${tap_count}" $tap_file
pushd $HOME
python metrics_generator.py "hpcg"
cp metrics_hpcg.json ${output_dir}/
popd