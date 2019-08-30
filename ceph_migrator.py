#! /usr/bin/python
"""This module has everything that this repo has to offer"""

import sys
import subprocess
from time import sleep
import click
import paramiko

DESTINATION_HOST = "example.com"
DESTINATION_USER = "username"
PORT = "19000"


@click.command()
@click.argument("src")
@click.argument("dest")
@click.option("--force", "-f", is_flag=True, default=False, help="Overwrite dest image")
def migrate(src, dest, force):
    """Function to migrate src_image to dest_img"""
    src_images = None
    if "/" not in src:
        sys.exit("First argument does not have a '/': " + src)
    else:
        src_pool = src.split("/")[0]
        src_image = src.split("/")[1]

    if "/" not in dest:
        print("src image name will be used for dest image name")
        dest_pool = dest
        dest_image = src_image
    else:
        dest_pool = dest.split("/")[0]
        dest_image = dest.split("/")[1]
        if dest_image == "*" or dest_image == "":
            print("Destination image has * in it. Source image name will be used")
            dest_image = src_image

    if "*" in src_image:
        all_images = get_all_images(src_pool)
        if src_image == "*":
            src_images = all_images
        else:
            src_image = src_image.replace("*", "")
            src_images = [
                image for image in all_images if src_image in image]
    else:
        if get_image_info(src_pool, src_image) is None:
            sys.exit("The src image does not exist. Trouble calling rbd info on it")

    destination_host = {"host": DESTINATION_HOST,
                        "user": DESTINATION_USER,
                        "port": PORT}

    # FIXME: Too many branches

    if src_images is None:
        if force:
            delete_image(dest_pool, dest_image,
                         DESTINATION_HOST, DESTINATION_USER)
        elif image_exists(dest_pool, dest_image, DESTINATION_HOST, DESTINATION_USER):
            sys.exit("The destination image exists. Please use --force/-f to overwrite")
        start_copy(src_image, src_pool, dest_image,
                   dest_pool, destination_host)
    else:
        for image in src_images:
            print("\nWorking on source image: " + image)
            if force:
                delete_image(dest_pool, image,
                             DESTINATION_HOST, DESTINATION_USER)
            elif image_exists(dest_pool, dest_image, DESTINATION_HOST, DESTINATION_USER):
                sys.exit("The destination image exists. Please use --force/-f to overwrite")
            start_copy(image, src_pool, image,
                       dest_pool, destination_host)
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


def start_copy(src_image, src_pool, dest_image, dest_pool, destination_host):
    """this is what will actually copy stuff"""
    host = destination_host["host"]
    user = destination_host["user"]
    port = destination_host["port"]

    remote_command = "nc -l {} | rbd import --no-progress - {}/{}".format(
        port, dest_pool, dest_image)
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
    migrate()
