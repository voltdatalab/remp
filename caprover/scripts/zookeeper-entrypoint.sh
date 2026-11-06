#!/bin/bash
# Preserve the pinned parent's two configuration adjustments, without sshd.
set -eu
sed -i -r 's|#(log4j.appender.ROLLINGFILE.MaxBackupIndex.*)|\1|g' "$ZK_HOME/conf/log4j.properties"
sed -i -r 's|#autopurge|autopurge|g' "$ZK_HOME/conf/zoo.cfg"

# zkServer.sh start-foreground execs Java. Deliver Docker SIGTERM to the JVM.
exec /opt/zookeeper-3.4.13/bin/zkServer.sh start-foreground
