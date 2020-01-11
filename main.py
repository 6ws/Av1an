#!/usr/bin/python3
"""
mkvmerge required (python-pymkv)
ffmpeg required
TODO:
DONE make encoding queue with limiting by workers
DONE make concatenating videos after encoding
DONE make passing your arguments for encoding,
make separate audio and encode it separately,
"""
import sys
import os
from os.path import join
from psutil import virtual_memory
from subprocess import Popen, PIPE, call
import argparse
import time
from shutil import rmtree
from math import ceil
from multiprocessing import Pool
try:
    import scenedetect
except:
    print('ERROR: No PyScenedetect installed, try: sudo pip install scenedetect')


DEFAULT_ENCODE = ' --passes=1 --tile-columns=2 --tile-rows=2  --cpu-used=8 --end-usage=q --cq-level=63 --aq-mode=0'
FFMPEG = 'ffmpeg -hide_banner -loglevel warning '


class ProgressBar:
    """
    Progress Bar for tracking encoding progress
    """

    def __init__(self,
                 prefix='',
                 suffix='',
                 decimals=1,
                 length=int(os.popen('stty size', 'r').read().split()[1]) - 10,
                 fill='█',
                 print_end="\r"):
        self.iteration = 0
        self.total = 0
        self.prefix = prefix
        self.suffix = suffix
        self.decimals = decimals
        self.length = length
        self.fill = fill
        self.print_end = print_end

    def print(self):
        if self.iteration == 0:
            percent = 0
            filled_length = 0
        else:
            percent = ("{0:." + str(self.decimals) + "f}").format(100 * (self.iteration / float(self.total)))
            filled_length = int(self.length * self.iteration // self.total)

        bar_size = (self.fill * filled_length) + '-' * (self.length - filled_length)
        print(f'\r{self.prefix}|{bar_size}| {percent}% {self.suffix}', end='')
        # Print New Line on Complete
        if self.iteration == self.total:
            print()

    def start(self):
        self.print()

    def tick(self):
        self.iteration += 1
        self.print()


# Progress Bar initialization
bar = ProgressBar()


def arg_parsing():
    """
    Command line parser
    Have default params
    """

    parser = argparse.ArgumentParser()
    parser.add_argument('--encoding_params', type=str, default=DEFAULT_ENCODE, help='AOMENC settings')
    parser.add_argument('--input_file', '-i', type=str, default='bruh.mp4', help='input video file')
    parser.add_argument('--num_worker', '-t', type=int, default=determine_resources(), help='number of encodes running at a time')
    return parser.parse_args()


def determine_resources():
    """
    Returns number of workers that machine can handle
    :return: int
    """
    cpu = os.cpu_count()
    ram = round(virtual_memory().total / 2**30)
    return ceil(min(cpu, ram/2))


def extract_audio(input_vid):
    """
    Extracting audio from video file
    Encoding audio to opus.
    Posible to -acodec copy to .mkv container without reencoding
    """
    cmd = f'{FFMPEG} -i {join(os.getcwd(),input_vid)} -vn -acodec copy {join(os.getcwd(),"temp","audio.mkv")}'
    Popen(cmd, shell=True).wait()


def split_video(input_vid):
    cmd2 = f'scenedetect -q -i {input_vid}  --output temp/split detect-content --threshold 50 split-video -c'
    call(cmd2, shell=True)
    print(f'Video {input_vid} splitted')


def get_video_queue(source_path):
    videos = []
    for root, dirs, files in os.walk(source_path):
        for file in files:
            f = os.path.getsize(os.path.join(root, file))
            videos.append([file, f])

    videos = sorted(videos, key=lambda x: -x[1])
    print(f'Splited videos: {len(videos)}')
    return videos


def encode(commands):
    """
    Passing encoding params to ffmpeg for encoding
    TODO:
    Replace ffmpeg with aomenc because ffmpeg libaom doen't work with parameters properly
    """

    cmd = f'{FFMPEG} {commands[0]}'
    Popen(cmd, shell=True,  stderr=PIPE).wait()

    # +1 to progress bar after encode is finished
    bar.tick()


def concat(input_video):
    """
    Using FFMPEG to concatenate all encoded videos to 1 file.
    Reading all files in A-Z order and saving it to concat.txt
    """
    with open(f'{os.getcwd()}/temp/concat.txt', 'w') as f:

        for root, firs, files in os.walk(join(os.getcwd(), 'temp', 'encode')):
            for file in sorted(files):
                f.write(f"file '{join(root, file)}'\n")

    cmd = f'{FFMPEG} -f concat -safe 0 -i {join(os.getcwd(), "temp", "concat.txt")} -i {join(os.getcwd(), "temp", "audio.mkv")} -c copy -y {input_video.split(".")[0]}_av1.webm'
    Popen(cmd, shell=True,  stderr=PIPE).wait()


def main(input_video, encoding_params, num_worker):

    # Make temporal directories, and remove them if already presented
    if os.path.isdir(join(os.getcwd(), "temp")):
        rmtree(join(os.getcwd(), "temp"))

    os.makedirs(join(os.getcwd(), 'temp', 'split'))
    os.makedirs(join(os.getcwd(), 'temp', 'encode'))

    # Extracting audio
    extract_audio(input_video)

    # Spliting video and sorting big-first
    split_video(input_video)
    vid_queue = get_video_queue('temp/split')
    files = [i[0] for i in vid_queue[:-1]]


    # Making list of commands for encoding
    commands = [(f'-i {join(os.getcwd(), "temp", "split", file)} -pix_fmt yuv420p -f yuv4mpegpipe - |' +
                f' aomenc -q {encoding_params} -o {join(os.getcwd(), "temp", "encode", file)} -', file) for file in files]

    # Creating threading pool to encode fixed amount of files at the same time
    print(f'Starting encoding with {num_worker} workers. \nParameters:{encoding_params}\nEncoding..')

    # Progress Bar
    bar.total = (len(vid_queue))
    bar.start()

    pool = Pool(num_worker)
    pool.map(encode, commands)

    # Merging all encoded videos to 1
    concat(input_video)


if __name__ == '__main__':

    args = arg_parsing()

    # Main thread
    start = time.time()
    main(args.input_file, args.encoding_params, args.num_worker)
    print(f'Completed in {round(time.time()-start, 1)} seconds')

    # Delete temp folders
    rmtree(join(os.getcwd(), "temp"))
