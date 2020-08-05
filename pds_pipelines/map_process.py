#!/usr/bin/env python

import os
import sys
import subprocess
import logging
import shutil
import argparse

from pysis import isis
from pysis.exceptions import ProcessError

from pds_pipelines.config import lock_obj, pds_log, default_namespace, workarea
from pds_pipelines.redis_queue import RedisQueue
from pds_pipelines.redis_lock import RedisLock
from pds_pipelines.redis_hash import RedisHash
from pds_pipelines.pds_logging import Loggy
from pds_pipelines.pds_process_logging import SubLoggy
from pds_pipelines.process import Process
from pds_pipelines.upc_process import generate_processes, process


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument('--key',
                        '-k',
                        dest='key',
                        help="Target key -- if blank, process first element in queue")
    parser.add_argument('--namespace',
                        '-n',
                        dest='namespace',
                        help="Queue namespace")
    args = parser.parse_args()
    return args


def main(user_args):
    key = user_args.key
    namespace = user_args.namespace

    if namespace is None:
        namespace = default_namespace

    work_dir = os.path.join(workarea, key)
    RQ_file = RedisQueue(key + '_FileQueue', namespace)
    RQ_work = RedisQueue(key + '_WorkQueue', namespace)
    RQ_zip = RedisQueue(key + '_ZIP', namespace)
    RQ_loggy = RedisQueue(key + '_loggy', namespace)
    RQ_final = RedisQueue('FinalQueue', namespace)
    RQ_recipe = RedisQueue(key + '_recipe', namespace)
    RHash = RedisHash(key + '_info')
    RHerror = RedisHash(key + '_error')
    RQ_lock = RedisLock(lock_obj)
    RQ_lock.add({'MAP':'1'})

    if int(RQ_file.QueueSize()) == 0:
        print("No Files Found in Redis Queue")
    elif RQ_lock.available('MAP'):
        jobFile = RQ_file.Qfile2Qwork(RQ_file.getQueueName(),
                                      RQ_work.getQueueName())

        # Setup system logging
        basename = os.path.splitext(os.path.basename(jobFile))[0]
        logger = logging.getLogger(key + '.' + basename)
        logger.setLevel(logging.DEBUG)

        logFileHandle = logging.FileHandler(pds_log + '/Service.log')

        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s, %(message)s')
        logFileHandle.setFormatter(formatter)
        logger.addHandler(logFileHandle)

        logger.info('Starting MAP Processing')

        loggyOBJ = Loggy(basename)

        # File Naming
        infile = os.path.join(work_dir, \
            os.path.splitext(os.path.basename(jobFile))[0] + '.input.cub')
        outfile = os.path.join(work_dir,
            os.path.splitext(os.path.basename(jobFile))[0] + '.output.cub')

        # Recipe Stuff
        status = 'success'
        recipe_string = RQ_recipe.QueueGet()
        no_extension_inputfile = os.path.join(work_dir, os.path.splitext(os.path.basename(jobFile))[0])
        process_props = {'no_extension_inputfile': no_extension_inputfile}
        processes, workarea_pwd = generate_processes(jobFile, recipe_string, logger, process_props = process_props)
        
        failing_command = process(processes, work_dir, logger)
        if failing_command:
            status = 'error'
        
        if status == 'success':

            if RHash.Format() == 'ISIS3':
                last_output = list(processes.items())[-1][-1]['to']
                last_output = last_output.split('+')[0]
                finalfile = os.path.join(work_dir, RHash.getMAPname() + '.cub')
            else:
                last_output = list(processes.items())[-1][-1]['dest']
                img_format = RHash.Format()

                if img_format == 'GeoTiff-BigTiff':
                    fileext = 'tif'
                elif img_format == 'GeoJPEG-2000':
                    fileext = 'jp2'
                elif img_format == 'JPEG':
                    fileext = 'jpg'
                elif img_format == 'PNG':
                    fileext = 'png'
                elif img_format == 'GIF':
                    fileext = 'gif'

                finalfile = os.path.join(work_dir, RHash.getMAPname() + '.' + fileext)
            shutil.move(last_output, finalfile)

            if RHash.getStatus() != 'ERROR':
                RHash.Status('SUCCESS')

            try:
                RQ_zip.QueueAdd(finalfile)
                logger.info('File Added to ZIP Queue')
            except:
                logger.error('File NOT Added to ZIP Queue')

            try:
                RQ_loggy.QueueAdd(loggyOBJ.Loggy2json())
                logger.info('JSON Added to Loggy Queue')
            except:
                logger.error('JSON NOT Added to Loggy Queue')

            RQ_work.QueueRemove(jobFile)
        elif status == 'error':
            RHash.Status('ERROR')
            if os.path.isfile(infile):
                os.remove(infile)

        if RQ_file.QueueSize() == 0 and RQ_work.QueueSize() == 0:
            try:
                RQ_final.QueueAdd(key)
                logger.info('Key %s Added to Final Queue: Success', key)
                logger.info('Job Complete')
            except:
                logger.error('Key NOT Added to Final Queue')
        else:
            logger.warning('Queues Not Empty: filequeue = %s  work queue = %s', str(
                RQ_file.QueueSize()), str(RQ_work.QueueSize()))


if __name__ == "__main__":
    sys.exit(main(parse_args()))
