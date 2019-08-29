#! /usr/bin/python
"""This module has everything that his repo has to offer"""
import sys
import subprocess
import click
import paramiko

DESTINATION_HOST = "example.com"
DESTINATION_USER = "username"
PORT = "19000"


@click.group()
def cli():
    """Top level group. I probably don't need this"""
    pass


@cli.command()
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

    if src_images is None:
        start_copy(src_image, src_pool, dest_image,
                   dest_pool, DESTINATION_HOST, PORT)
    else:
        for image in src_images:
            start_copy(image, src_pool, image,
                       dest_pool, DESTINATION_HOST, PORT)


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


def start_copy(src_image, src_pool, dest_image, dest_pool, dest_ip, port):
    """this is what will actually copy stuff"""

    # Stuff that happens remotely
    remote_command = "nc -l {} | rbd import --no-progress - {}/{}".format(
        port, dest_pool, dest_image)
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(DESTINATION_HOST, username=DESTINATION_USER)
    stdin, stdout, stderr = client.exec_command(remote_command, get_pty=True)

    # Stuff that happens on the local host
    rbd_command = "rbd --no-progress export {}/{} -".format(
        src_pool, src_image)
    nc_command = "nc {} {}".format(dest_ip, port)
    print(rbd_command)
    print(nc_command)
    rbd_command = subprocess.Popen(rbd_command.split(), stdout=subprocess.PIPE)
    nc_command = subprocess.Popen(
        nc_command.split(), stdin=rbd_command.stdout, stdout=subprocess.PIPE)
    return nc_command.communicate()[0]


if __name__ == "__main__":
    cli()
