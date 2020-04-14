# Copyright 2020 Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

FROM amazonlinux:1    
ENV USER efauser 
RUN yum update -y 
RUN yum install -y which gcc-c++ libtool autoconf automake util-linux make tar.x86_64 \
    iproute2 gcc-gfortran openssh-server openssh-client python36 python36-pip \
    build-essential wget curl git wget pkg-config zip unzip libnl3-devel emacs \
    diffutils aws-cli && yum -y clean all
RUN pip-3.6 install supervisor

## The installation below is required for updating gcc to version 9.2
RUN yum install -y vim bzip2 gcc gmp-devel libmpc-devel mpfr-devel && yum -y clean all


RUN useradd -ms /bin/bash $USER
ENV HOME /home/$USER
ARG LIBFABRIC_JOB_TYPE="master"
ARG MPI_TYPE="openmpi" 
ARG MPI_INSTALL_PATH="/opt/amazon/openmpi/"
ARG S3_REPO
ARG S3_BUCKET
ARG NUM_NODES=2
ARG GCC_VERSION=9.2.0
ENV LIBFABRIC_JOB_TYPE=$LIBFABRIC_JOB_TYPE \
    MPI_TYPE=$MPI_TYPE \
    MPI_INSTALL_PATH=$MPI_INSTALL_PATH \
    FABTESTS_INSTALL_PATH=$HOME/libfabric/fabtests/install \
    S3_BUCKET=$S3_BUCKET \
    S3_REPO=$S3_REPO \
    NUM_NODES=$NUM_NODES

#####################################################
## SSH SETUP
ENV SSHDIR $HOME/.ssh
RUN mkdir -p ${SSHDIR} \
	&& touch ${SSHDIR}/sshd_config \
	&& ssh-keygen -t rsa -f ${SSHDIR}/ssh_host_rsa_key -N '' \
	&& cp ${SSHDIR}/ssh_host_rsa_key.pub ${SSHDIR}/authorized_keys \
	&& cp ${SSHDIR}/ssh_host_rsa_key ${SSHDIR}/id_rsa \
	&& echo "    IdentityFile ${SSHDIR}/id_rsa" >> ${SSHDIR}/config \
	&& echo "    StrictHostKeyChecking no" >> ${SSHDIR}/config \
	&& echo "    UserKnownHostsFile /dev/null" >> ${SSHDIR}/config \
	&& echo "    Port 2022" >> ${SSHDIR}/config \
	&& echo 'Port 2022' >> ${SSHDIR}/sshd_config \
	&& echo 'UsePrivilegeSeparation no' >> ${SSHDIR}/sshd_config \
	&& echo "HostKey ${SSHDIR}/ssh_host_rsa_key" >> ${SSHDIR}/sshd_config \
	&& echo "PidFile ${SSHDIR}/sshd.pid" >> ${SSHDIR}/sshd_config \
	&& chmod -R 600 ${SSHDIR}/* \
	&& chown -R ${USER}:${USER} ${SSHDIR}/

# check if ssh agent is running or not, if not, run
RUN eval `ssh-agent -s` && ssh-add ${SSHDIR}/id_rsa

#################################################
## EFA and MPI SETUP
RUN if [ "${LIBFABRIC_JOB_TYPE}" = "aws-efa-installer-dev-latest" ]; then \
	EFA_INSTALLER_URL="https://s3-us-west-2.amazonaws.com/aws-efa-installer-dev/aws-efa-installer-latest.tar.gz"; \
	else EFA_INSTALLER_URL="https://s3-us-west-2.amazonaws.com/aws-efa-installer/aws-efa-installer-latest.tar.gz" ; fi \
	&& curl -o efa-installer.tar.gz ${EFA_INSTALLER_URL} \
	&& tar -xf efa-installer.tar.gz \
	&& cd aws-efa-installer \
	&& ./efa_installer.sh -y --skip-kmod --skip-limit-conf --no-verify

## Install RDMA core packages from installer v1.8.1.
RUN if [ "${LIBFABRIC_JOB_TYPE}" = "master" ]; then \
    curl -o efa-installer-1.8.1.tar.gz https://s3-us-west-2.amazonaws.com/aws-efa-installer/aws-efa-installer-1.8.1.tar.gz; \
    tar -xf efa-installer-1.8.1.tar.gz --transform='s/aws-efa-installer/aws-efa-installer-1.8.1/'; \
    pushd aws-efa-installer-1.8.1/RPMS/ALINUX1; \
    rm efa*.rpm openmpi*.rpm libfabric*.rpm; \
    yum -y install *.rpm; \
    popd; \
    fi

## Install Intel MPI (when $MPI_TYPE = "intelmpi")
RUN if [ "$MPI_TYPE" = "intelmpi" ]; then \
	curl -O https://s3.us-west-2.amazonaws.com/subspace-intelmpi/l_mpi_2019.6.166.tgz; \
	tar -xf l_mpi_2019.6.166.tgz; cd l_mpi_2019.6.166; \
        ./install.sh -s silent.cfg --accept_eula; fi

###################################################
## Download Libfabric
RUN git clone https://github.com/ofiwg/libfabric

## Install Libfabric
RUN pushd libfabric \
    && if [ ${LIBFABRIC_JOB_TYPE} = "aws-efa-installer-dev-latest" ]; then \
    . /etc/profile.d/efa.sh; \
    # Checkout the bugfix branch for the given release so that fabtests is
    # compatible. If the branch isn't found use master.
    ofi_ver=$(fi_info --version | grep 'libfabric api' | awk '{print $3}'); \
    git checkout "v${ofi_ver}.x"; \
    else ./autogen.sh; \
    ./configure --prefix=${HOME}/libfabric/install \
    --disable-verbs --disable-usnic --disable-rstream --disable-rxd; \
    make -j4; \
    make install; fi \
    && popd

## Install fabtests
RUN if [ "${LIBFABRIC_JOB_TYPE}" = "aws-efa-installer-dev-latest" ]; then \
	LIBFABRIC_INSTALL_PATH="/opt/amazon/efa"; \
	else LIBFABRIC_INSTALL_PATH="$HOME/libfabric/install"; fi \
	&& pushd libfabric/fabtests \
	&& ./autogen.sh \
	&& ./configure --prefix=${FABTESTS_INSTALL_PATH} \
	--with-libfabric=${LIBFABRIC_INSTALL_PATH} \
	&& make -j 4 \
	&& make install \
	&& PROVIDER="efa" \
	&& EXCLUDE=${FABTESTS_INSTALL_PATH}/share/fabtests/test_configs/${PROVIDER}/${PROVIDER}.exclude \
	&& echo "# dgram_pingpong failed as reported in https://t.corp.amazon.com/EFATT-47" >> $EXCLUDE \
	&& echo "dgram_pingpong" >> $EXCLUDE \
	&& popd

## Install IMB
RUN git clone https://github.com/intel/mpi-benchmarks.git \
	&& pushd mpi-benchmarks \
	&& export CC=${MPI_INSTALL_PATH}/bin/mpicc \
	&& export CXX=${MPI_INSTALL_PATH}/bin/mpicxx \
	&& export CPPFLAGS=-DCHECK \
	&& make IMB-MPI1 \
	&& popd

## Install OMB
RUN curl -O https://s3.us-west-2.amazonaws.com/subspace-benchmarks-files/spack_mirror/osu-micro-benchmarks/osu-micro-benchmarks-5.6.tar.gz \
	&& tar -zxf osu-micro-benchmarks-5.6.tar.gz \
	&& cd osu-micro-benchmarks-5.6/ \
	&& CC=${MPI_INSTALL_PATH}/bin/mpicc CXX=${MPI_INSTALL_PATH}/bin/mpicxx ./configure --prefix=/omb \
	&& make \
	&& make install

# Install hpcg
RUN git clone -b HPCG-release-3-0-branch https://github.com/hpcg-benchmark/hpcg.git \
	&& export PATH=${MPI_INSTALL_PATH}/bin:$PATH \
	&& mkdir hpcg/build \
	&& pushd hpcg/build \
	&& ../configure MPI_GCC_OMP \
	&& make \
	&& popd



###########################################################
# Following commands are for hpcc installation and compile.
# hpcc requires Intel MKL and newer version of GCC.
#########################################################
## Install Intel MKL
RUN yum-config-manager --add-repo https://yum.repos.intel.com/setup/intelproducts.repo; \
    yum -y install intel-mkl-2020.0-088; \
    yum -y clean all

## Update gcc to 9.2.0, since hpcc build need the -mavx512f, -mavx512cd, -mavx512er flags,
## the default gcc version 4.8 doesn't support those flags.
## This is very time consuming in Docker.
RUN wget http://gnu.mirror.constant.com/gcc/gcc-${GCC_VERSION}/gcc-${GCC_VERSION}.tar.gz; \
    echo "update gcc to ${GCC_VERSION}"; \
    tar -vzxf gcc-${GCC_VERSION}.tar.gz; \
    mkdir gcc-build; \
    cd gcc-build; \
    ../gcc-${GCC_VERSION}/configure --enable-languages=c,c++ --disable-multilib; \
    make -j 2; \
    make install; \
    export PATH=/usr/local/bin:$PATH; \
    export LD_LIBRARY_PATH=/usr/local/lib64:$LD_LIBRARY_PATH; \
    cd ../ \
    rm -r gcc-build; \
    rm gcc-${GCC_VERSION}.tar.gz

## install and compile hpcc
RUN git clone https://github.com/yangxuserene/hpcc.git
RUN cd hpcc/hpcc-1.5.0 \
    && export PATH=${MPI_INSTALL_PATH}/bin:$PATH \
    && make arch=xyangamz-docker

## supervisor container startup

COPY conf/supervisord/supervisord.conf /etc/supervisor/supervisord.conf
COPY supervised-scripts/run.sh supervised-scripts/run.sh
COPY supervised-scripts/common.sh supervised-scripts/common.sh

# let's only run hpcg for now. will add hpcc run bash script later
COPY supervised-scripts/run_hpcg.sh supervised-scripts/run_hpcg.sh
#COPY supervised-scripts/run_imb.sh supervised-scripts/run_imb.sh
#COPY supervised-scripts/run_omb.sh supervised-scripts/run_omb.sh
#COPY supervised-scripts/run_fabtests.sh supervised-scripts/run_fabtests.sh
#COPY supervised-scripts/metrics_generator.py $HOME/metrics_generator.py

EXPOSE 2022
COPY batch-runtime-scripts/entry-point.sh batch-runtime-scripts/entry-point.sh
RUN chmod 755 batch-runtime-scripts/entry-point.sh

CMD /batch-runtime-scripts/entry-point.sh;
