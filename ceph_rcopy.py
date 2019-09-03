#! /usr/bin/python
"""This module has everything that this repo has to offer"""

import sys
import os
import subprocess
from time import sleep
import click
import paramiko

DESTINATION_USER = os.environ.get("USER")
if DESTINATION_USER is None:
    sys.exit("There's no destination user set. Set the environment variable USER")
PORT = os.environ.get("PORT", "19000")


@click.command()
@click.argument("src")
@click.argument("dest")
@click.option("--force", "-f", is_flag=True, default=False, help="Overwrite destination image if it exists")
@click.option("--data-pool", "-e", help="Specify data pool for EC pool")
@click.option("--destination-host", "-h", help="Specify the destination host ip/name")
def rcopy(src, dest, force, destination_host, data_pool=None):
    """
    Copy src image to dest image.

    Arguments:

        src:

        Specify source pool and image as source-pool/source-image. Where source-image can be * or contain *.

        Examples: pool/particular-image or pool/multiple-match* or pool/* for all images in a pool

        dest:

        Specify destination pool and image as dest-image/dest-pool. You can also only provide dest-pool

        Examples: pool/particular-image or pool/* or pool.

        You must not specify a particular image name if migrating multiple images.

    """
    if destination_host is None:
        destination_host = os.environ.get("destination_host")
    if destination_host is None:
        sys.exit(
            "Either set the environment variable destination_host or provide it via the command line")

    if "/" not in src:
        sys.exit("First argument does not have a '/': " + src)
    else:
        src_pool = src.split("/")[0]
        src_image = src.split("/")[1]

    if "*" in src_image:
        all_images = get_all_images(src_pool)
        if src_image == "*":
            src_images_list = all_images
        else:
            src_image = src_image.replace("*", "")
            src_images_list = [
                image for image in all_images if src_image in image]
        dest_images_list = [src_images_list]
    else:
        if get_image_info(src_pool, src_image) is None:
            sys.exit("The src image does not exist. Trouble calling rbd info on it")
        src_images_list = [src_image]

    if "/" in dest:
        dest_pool = dest.split("/")[0]
        dest_image = dest.split("/")[1]
        if dest_image == "*" or dest_image == "":
            dest_images_list = src_images_list
        else:
            dest_images_list = [dest_image]
    else:
        dest_pool = dest
        dest_images_list = src_images_list

    assert len(src_images_list) == len(
        dest_images_list), "Number of source and destination images don't match"

    destination = {"host": destination_host,
                   "user": DESTINATION_USER,
                   "port": PORT}

    for pair in zip(src_images_list, dest_images_list):
        src_image = pair[0]
        dest_image = pair[1]
        print("Migrating {}/{} to {}/{}".format(src_pool,
                                                src_image, dest_pool, dest_image))
        if force:
            delete_image(dest_pool, dest_image,
                         destination_host, DESTINATION_USER)
        elif image_exists(dest_pool, dest_image, destination_host, DESTINATION_USER):
            sys.exit(
                "The destination image exists. Please use --force/-f to overwrite")
        start_copy(src_image, src_pool, dest_image,
                   dest_pool, destination, data_pool)

        if len(src_images_list) > 1:
            sleep(5)


def get_image_info(pool, image):
    """Returns information about image or None if the image does not exist"""
    command = "rbd info --pool {} --image {}".format(pool, image)
    try:
        info = subprocess.check_output(command.split())
    except subprocess.CalledProcessError as error:
        print(error)
        return None
    return info


def get_all_images(pool):
    """Returns a list of all rbd images in a pool"""
    command = "rbd ls --pool {}".format(pool)
    images = subprocess.check_output(command.split())
    images = filter(None, images.split("\n"))
    return images


def get_ssh_client(ip, user):
    """Returns a paramiko ssh client that's connected.

    The caller should close the session"""
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(ip, username=user)
    return client


def image_exists(pool, image, ip, user):
    """Test if the image exists or not in the remote rbd pool"""
    command = "rbd info --pool {} --image {}".format(pool, image)
    client = get_ssh_client(ip, user)
    stdin, stdout, stderr = client.exec_command(command)
    exit_status = stderr.channel.recv_exit_status()
    client.close()
    return exit_status == 0


def delete_image(pool, image, ip, user):
    """Delete image in remote rbd pool"""
    command = "rbd rm --pool {} --image {}".format(pool, image)
    client = get_ssh_client(ip, user)
    stdin, stdout, stderr = client.exec_command(command)
    exit_status = stderr.channel.recv_exit_status()
    error = stderr.readlines()
    client.close()

    if exit_status == 0:
        print("Destination image was deleted. We will now recreate it")
    elif exit_status == 2:
        print("Destination image does not exist. We will create a new one")
    else:
        print("Failed to delete image {}/{}".format(pool, image))
        print("Exit status: " + str(exit_status))
        print(error)
        sys.exit(1)


def start_copy(src_image, src_pool, dest_image, dest_pool, destination_host, data_pool):
    """this is what will actually copy stuff"""
    host = destination_host["host"]
    user = destination_host["user"]
    port = destination_host["port"]

    remote_command = "nc -l {} | rbd import --no-progress - {}/{}".format(
        port, dest_pool, dest_image)

    if data_pool:
        remote_command += " --data-pool {}".format(data_pool)

    rbd_command = "rbd --no-progress export {}/{} -".format(
        src_pool, src_image)
    nc_command = "nc {} {}".format(host, port)

    print("remote_command: " + remote_command)
    print("rbd_command: " + rbd_command)
    print("nc_command: " + nc_command)

    # Stuff that happens remotely
    client = get_ssh_client(host, user)
    stdin, stdout, stderr = client.exec_command(remote_command)
    # wait for netcat to start listening
    sleep(2)

    # Stuff that happens on the local host
    rbd_command = subprocess.Popen(rbd_command.split(), stdout=subprocess.PIPE)
    nc_command = subprocess.Popen(
        nc_command.split(), stdin=rbd_command.stdout, stdout=subprocess.PIPE)
    output = nc_command.communicate()[0]

    client.close()
    return output


if __name__ == "__main__":
    rcopy()
