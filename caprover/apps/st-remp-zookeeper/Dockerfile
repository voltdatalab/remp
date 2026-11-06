# Minimal containment only: retain ZooKeeper/data compatibility, skip sshd.
FROM wurstmeister/zookeeper@sha256:7a7fd44a72104bfbd24a77844bad5fabc86485b036f988ea927d1780782a6680

# Refuse unexpected upstream startup bytes before replacing its invocation.
RUN printf '%s  /usr/bin/start-zk.sh\n' 'b795ec48daa49c1acf67fb23617f23a54b60de6ddf651c0f24546604561e9a87' | sha256sum -c -
COPY zookeeper-entrypoint.sh /usr/local/bin/remp-zookeeper-entrypoint.sh

# The pinned parent has no ENTRYPOINT. Exec-form avoids the parent's SSH CMD.
CMD ["/bin/bash", "/usr/local/bin/remp-zookeeper-entrypoint.sh"]
