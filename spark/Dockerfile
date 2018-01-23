FROM scannerresearch/esper-base:cpu

WORKDIR /opt
RUN wget -q http://apache.mirrors.tds.net/spark/spark-2.2.1/spark-2.2.1-bin-hadoop2.7.tgz && \
    tar -xf spark-2.2.1-bin-hadoop2.7.tgz && \
    rm spark-2.2.1-bin-hadoop2.7.tgz
WORKDIR /opt/spark-2.2.1-bin-hadoop2.7
CMD ./sbin/start-master.sh -h 0.0.0.0 && \
    ./sbin/start-slave.sh spark://localhost:7077 && \
    sleep infinity