# ceph-rcopy

## What is this?

A simple script that can migrate rbd images in one ceph to an rbd pool on other
ceph.

It uses netcat to join the rbd import and rbd exports over network.
This means that the network traffic is **unencrypted**.  So you should probably use it only in private networks or subnets that you control and trust.
Maybe in the future I'll use ssh as transport which will add encryption, but it would be significantly slower than netcat.

## How to run it?

It requires paramiko and click

* `yum install python2-click python-paramiko -y`

Just run ./ceph-rcopy.py --help

## How does it work and what are you doing?

It starts a netcat listener on the recieving host, and then sends the data from the host executing the script.

I am not using python sockets or python-rbd libraries because:

1. Running python code on the remote host to listen on a socket and perform an rbd import would require way more work. The easiest thing to do is run the commands on the remote host that already exist on that host (`netcat -l PORT | rbd import name`).
2. And if I already have to make calls to those commands on the remote host, I might as well do the same on the source machine.

## Why are you doing this?

Becasue @radonm wanted this to migrate ceph images between our various ceph clusters.
