# Update this digest deliberately, then rerun connected and offline rebuild checks.
FROM ubuntu:24.04@sha256:2198e4c65076e9cb0b3d695219df667c0e3b0072da64ca3c2648aca17dcecaf5
COPY [".", "/workspace/checkout with spaces/"]
WORKDIR /workspace/checkout with spaces
RUN bash bin/linux-host.sh install && \
    mkdir /tmp/empty-skel && \
    useradd --create-home --skel /tmp/empty-skel --uid 1100 --shell /bin/bash rebuild && \
    chown -R rebuild:rebuild /workspace
USER rebuild
ENV HOME=/home/rebuild
RUN bash bin/docker-rebuild-verify.sh provision
CMD ["bash", "bin/docker-rebuild-verify.sh", "offline"]
