ARG base_name
FROM ${base_name}:cpu
ARG spark_version=2.4.0

WORKDIR /opt
RUN wget -q http://apache.mirrors.tds.net/spark/spark-${spark_version}/spark-${spark_version}-bin-hadoop2.7.tgz && \
    tar -xf spark-${spark_version}-bin-hadoop2.7.tgz && \
    rm spark-${spark_version}-bin-hadoop2.7.tgz
WORKDIR /opt/spark-${spark_version}-bin-hadoop2.7
RUN rm /usr/bin/python && ln -s /usr/bin/python3 /usr/bin/python
CMD ./sbin/start-master.sh -h 0.0.0.0 && \
    ./sbin/start-slave.sh spark://localhost:7077 && \
    sleep infinity
