"""
 Parse the csv files in results and generate metrics
 data in JSON file to be sent to CloudWatch in nightly-tests
 scripts.
"""

import glob
import os
import sys
import csv
import json


class SubspaceBenchmarks(object):

    def __init__(self, test_name):
        """
        @test_name: the name of the test for a certain app
        """
        self.test_name = test_name

    def generate_metrics_imb(self):
        """
        There is no csv generated by IMB yet. Need to implement
        in the future.
        """
        pass

    def generate_metrics_stream(self):
        """
        generate metrics for STREAM
        Namespace: stream
        MetricName: function (copy, add, scale, triad)
        Dimensions: Thread
        Value: memory bandwidth (in GB/s)
        """
        test_dir = "results/stream"
        rows = []
        filepath = os.path.join(test_dir, "*.csv")
        filenames = glob.glob(filepath)
        namespace = "stream"
        print(" ====== start generating metrics for Namespace: %s ====" % namespace)
        data = {'Namespace': namespace, 'MetricData': []}
        for filename in filenames:
            with open(filename, 'r') as csvfile:
                csvreader = csv.reader(csvfile)
                fields = next(csvreader)
                for row in csvreader:
                    rows.append(row)
            for row in rows:
                thread = row[0]
                function = row[1]
                rate = float(row[2]) / (2 ** 10.)  # cloudwatch treat 1k as 1000
                print("MetricName: %s, thread: %s, rate: %f GB/s" % (function, thread, rate))
                metricdata = {'MetricName': function}
                dimensions = [{'Name': 'Thread', 'Value': str(thread) + ' threads'},]
                metricdata['Dimensions'] = dimensions
                metricdata['Unit'] = 'Gigabytes/Second'
                metricdata['Value'] = rate
                data['MetricData'].append(metricdata)
        with open('metrics_{}.json'.format(namespace), 'w') as json_output:
            json.dump(data, json_output)

    def generate_metrics_lammps(self):
        """
        generate metrics for LAMMPS
        Namespace: lammps
        MetricName: the input file (in.ij, in.eam, in.chain etc.)
        Dimensions: Thread, Node
        Value: loop time /s
        """
        test_dir = "results/lammps"
        rows = []
        filepath = os.path.join(test_dir, "*.csv")
        filenames = glob.glob(filepath)
        namespace = "lammps"
        print(" ====== start generating metrics for Namespace: %s ====" % namespace)
        data = {'Namespace': namespace, 'MetricData': []}
        for filename in filenames:
            with open(filename, 'r') as csvfile:
                csvreader = csv.reader(csvfile)
                fields = next(csvreader)
                for row in csvreader:
                    rows.append(row)

            for row in rows:
                thread = row[0]
                node = row[1]
                loop_time = float(row[2])
                input_file = row[3]
                print("MetricName: %s, thread: %s, node: %s, loop time/s: %f" \
                      % (input_file, thread, node, loop_time))
                metricdata = {'MetricName': input_file}
                dimensions = [{'Name': 'Thread', 'Value': str(thread) + ' threads'},
                              {'Name': 'Node', 'Value': str(node) + ' nodes'},]
                metricdata['Dimensions'] = dimensions
                metricdata['Unit'] = 'Seconds'
                metricdata['Value'] = loop_time
                data['MetricData'].append(metricdata)
        with open('metrics_{}.json'.format(namespace), 'w') as json_output:
            json.dump(data, json_output)

    def generate_metrics_wrfv(self):
        """
        put metrics for WRFV
        Namespace: wrfv
        MetricName: main_time
        Dimensions: Thread, Node
        Value: main time (in sec)
        """
        test_dir = "results/wrfv"
        rows = []
        filepath = os.path.join(test_dir, "*.csv")
        filenames = glob.glob(filepath)
        namespace = "wrfv"
        metricname = "main_time"
        print(" ====== start generating metrics for Namespace: %s ====" % namespace)
        data = {'Namespace': namespace, 'MetricData': []}
        for filename in filenames:
            with open(filename, 'r') as csvfile:
                csvreader = csv.reader(csvfile)
                fields = next(csvreader)
                for row in csvreader:
                    rows.append(row)
            for row in rows:
                thread = row[0]
                node = row[1]
                main_time = float(row[3])
                print("MetricName: %s, thread: %s, node: %s, main_time: %f" \
                      % (metricname, thread, node, main_time))
                metricdata = {'MetricName': metricname}
                dimensions = [{'Name': 'Thread', 'Value': str(thread) + ' threads'},
                              {'Name': 'Node', 'Value': str(node) + ' nodes'},]
                metricdata['Dimensions'] = dimensions
                metricdata['Unit'] = 'Seconds'
                metricdata['Value'] = main_time
                data['MetricData'].append(metricdata)
        with open('metrics_{}.json'.format(namespace), 'w') as json_output:
            json.dump(data, json_output)

    def generate_metrics_hpcg(self):
        """
        put metrics for hpcg
        Namespace: hpcg
        MetricName: GFlops/s
        Dimensions: Thread, Node
        Value: GFlops/s
        """
        test_dir = "results/hpcg"
        rows = []
        filepath = os.path.join(test_dir, "*.csv")
        filenames = glob.glob(filepath)
        namespace = "hpcg"
        metricname = "GFlops/s"
        print(" ====== start generating metrics for Namespace: %s ====" % namespace)
        data = {'Namespace': namespace, 'MetricData': []}
        for filename in filenames:
            with open(filename, 'r') as csvfile:
                csvreader = csv.reader(csvfile)
                fields = next(csvreader)
                for row in csvreader:
                    rows.append(row)

            for row in rows:
                thread = row[0]
                node = row[1]
                gflop = float(row[2])
                print("MetricName: %s, thread: %s, node: %s, gflop: %f" \
                      % (metricname, thread, node, gflop))
                metricdata = {'MetricName': metricname}
                dimensions = [{'Name': 'Thread', 'Value': str(thread) + ' threads'},
                              {'Name': 'Node', 'Value': str(node) + ' nodes'},]
                metricdata['Dimensions'] = dimensions
                metricdata['Unit'] = 'None'
                metricdata['Value'] = gflop
                data['MetricData'].append(metricdata)
        with open('metrics_{}.json'.format(namespace), 'w') as json_output:
            json.dump(data, json_output)

    def generate_metrics_omb(self):
        """
        generate metrics for OMB
        Namespace: the omb test suite (omb-collective, omb-pt2pt, etc.)
        MetricName: test name (osu_latency, osu_bw, osu_mbw_mr, etc.)
        Dimensions: Thread, Node
        Value: bandwidth (GB/s), latency (milisecond)
               or message rate, depends on the test name.
        """
        if "collective" in self.test_name:
            namespace = "omb-collective"
            test_dir = "results/omb/collective"
            test_list = [
                "osu_allgather",
                "osu_allgatherv",
                "osu_allreduce",
                "osu_alltoall",
                "osu_alltoallv",
                "osu_bcast",
                "osu_gather",
                "osu_gatherv",
                "osu_reduce",
                "osu_reduce_scatter",
                "osu_scatter",
                "osu_scatterv"
            ]
        elif "pt2pt" in self.test_name:
            namespace = "omb-pt2pt"
            test_dir = "results/omb/pt2pt"
            test_list = [
                "osu_latency",
                "osu_bw",
                "osu_bibw",
                "osu_latency_mt",
                "osu_mbw_mr",
                "osu_multi_lat"
            ]

        elif "onesided" in test_name:
            namespace = "omb-onesided"
            test_dir = "results/omb/one-sided"
            test_list = [
                "osu_acc_latency",
                "osu_cas_latency",
                "osu_fop_latency",
                "osu_get_acc_latency",
                "osu_get_bw",
                "osu_get_latency",
                "osu_put_bibw",
                "osu_put_bw",
                "osu_put_latency"
            ]
        else:
            raise ValueError("test suite must be 'collective', 'pt2pt', or 'onesided'! ")

        print(" ====== start generating metrics for Namespace: %s ====" % namespace)
        data = {'Namespace': namespace, 'MetricData': []}
        for test in test_list:
            metricname = test
            rows = []
            filepath = os.path.join(test_dir, test, "*.csv")
            filenames = glob.glob(filepath)
            for filename in filenames:
                with open(filename, 'r') as csvfile:
                    csvreader = csv.reader(csvfile)
                    for row in csvreader:
                        rows.append(row)

                for row in rows:
                    size = row[0]
                    if test == "osu_mbw_mr":
                        unit = 'None'
                        value = float(row[2])
                    elif "bw" in test:
                        unit = "Gigabytes/Second"
                        value = float(row[1]) / (2 ** 10.)  # cloudwatch treat 1k as 1000
                    else:
                        unit = "Microseconds"
                        value = float(row[1])
                    print("MetricName: %s, msg size: %s bytes, value: %f, unit: %s" \
                          % (metricname, size, value, unit))
                    metricdata = {'MetricName': metricname}
                    dimensions = [{'Name': 'Byte', 'Value': str(size) + ' bytes'},]
                    metricdata['Dimensions'] = dimensions
                    metricdata['Unit'] = unit
                    metricdata['Value'] = value
                    data['MetricData'].append(metricdata)
            with open('metrics_{}.json'.format(namespace), 'w') as json_output:
                json.dump(data, json_output)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise ValueError(" Usage: python metrics_generator.py <test_name>")
    test_name = sys.argv[1]
    sb = SubspaceBenchmarks(test_name)
    if "hpcg" in test_name:
        sb.generate_metrics_hpcg()
    elif "omb" in test_name:
        sb.generate_metrics_omb()
    elif "imb" in test_name:
        sb.generate_metrics_imb()
    elif "stream" in test_name:
        sb.generate_metrics_stream()
    elif "wrfv" in test_name:
        sb.generate_metrics_wrfv()
    elif "lammps" in test_name:
        sb.generate_metrics_lammps()
    else:
        raise NotImplementedError("app name unknown!")
