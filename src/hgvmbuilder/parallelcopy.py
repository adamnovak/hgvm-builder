#!/usr/bin/env python
# hgvm-builder parallelcopy.py: Command-line tool to copy between toil-vg IOStores
"""
Copies a directory from one IOStore (filesystem, AWS, Azure) to another.
Basically a Toil-based rclone.

"""


import argparse
import sys
import os
import os.path
import random
import subprocess
import shutil
import itertools
import glob
import doctest
import re
import json
import collections
import time
import timeit
import tempfile
import traceback
import fnmatch

import toil
import toil.version
from toil.common import Toil
from toil.job import Job
from toil.realtimeLogger import RealtimeLogger

from toil_vg.iostore import IOStore

from multiprocessing.pool import ThreadPool

def parse_args(args):
    """
    Takes in the command-line arguments list (args), and returns a nice argparse
    result with fields for all the options.
    
    Borrows heavily from the argparse documentation examples:
    <http://docs.python.org/library/argparse.html>
    """
    
    # Construct the parser (which is stored in parser)
    # Module docstring lives in __doc__
    # See http://python-forum.com/pythonforum/viewtopic.php?f=3&t=36847
    # And a formatter class so our examples in the docstring look good. Isn't it
    # convenient how we already wrapped it to 80 characters?
    # See http://docs.python.org/library/argparse.html#formatter-class
    parser = argparse.ArgumentParser(description=__doc__, 
        formatter_class=argparse.RawDescriptionHelpFormatter)
    
    # Add the Toil options so the job store is the first argument
    Job.Runner.addToilOptions(parser)
    
    # General options
    parser.add_argument("in_store", type=IOStore.absolute,
        help="input IOStore to download from")
    parser.add_argument("out_store", type=IOStore.absolute,
        help="output IOStore to put things in")
    parser.add_argument("--pattern", default="*", 
        help="fnmatch-style pattern for file names to copy")
    parser.add_argument("--overwrite", default=False, action="store_true",
        help="overwrite existing files")
    parser.add_argument("--check_size", default=False, action="store_true",
        help="check sizes on existing files and replace if wrong")
    parser.add_argument("--batch_size", type=int, default=1000,
        help="number of files to copy in a batch")
    
    # The command line arguments start with the program name, which we don't
    # want to treat as an argument for argparse. So we remove it.
    args = args[1:]
        
    return parser.parse_args(args)
   
def group(iterable, max_count):
    """
    Batch up iterable results. Pads with None.
    
    See <http://stackoverflow.com/a/8290490/402891>
    
    """
    
    batch = []
    
    while True:
        try:
            # Grab the next thing from the underlying iterator and put it in our
            # batch
            batch.append(iterable.next())
        except StopIteration:
            # Underlying iterator ran out. Yield what we have and stop.
            yield batch
            break
            
        if len(batch) >= max_count:
            # If we have enough items, yield a batch and start a new one
            yield batch
            batch = []

def copy_everything(job, options):
    """
    Download the file list and copy all the files.
    
    """
    
    # Set up the IO stores.
    in_store = IOStore.get(options.in_store)
    out_store = IOStore.get(options.out_store)
    
    batch_count = 0;
    
    # List all the files.
    blobs_iterator = in_store.list_input_directory("", recursive=True)
    
    # Make an iterator that filters them
    filtered_iterator = (x for x in blobs_iterator if
        fnmatch.fnmatchcase(x, options.pattern))
    
    # Batch them up
    for batch in group(filtered_iterator, options.batch_size):
        
        # For every batch, strip out any Nones that got put in when grouping
        batch = [x for x in batch if x is not None]
    
        # Copy everything in that batch
        job.addChildJobFn(copy_batch, options, batch, cores=1, memory="1G",
            disk="10G")
            
        batch_count += 1
        
        if batch_count % 10 == 0:
        
            RealtimeLogger.info("Queued {} batches...".format(
                batch_count))
            
    RealtimeLogger.info("Queued {} total batches".format(batch_count))
    
def copy_batch(job, options, batch):
    """
    Copy a batch of files from input to output.
    """
        
    RealtimeLogger.info("Copying a batch")
        
    # Set up the IO stores.
    in_store = IOStore.get(options.in_store)
    out_store = IOStore.get(options.out_store)

    # Start some threads
    pool = ThreadPool(10)
    
    
    def download(filename):
        """
        Download each file
        """
        
        try:
        
            if (not options.overwrite) and out_store.exists(filename):
                # File exists. But make sure its size is correct.
                
                if not options.check_size:
                    # Skip existing file. No need to check the length.
                    RealtimeLogger.info("Skipped {}".format(filename))
                    return
                
                out_size = out_store.get_size(filename)
                in_size = in_store.get_size(filename)
                if out_size != in_size:
                    # Complain about size mismatch and copy
                    RealtimeLogger.warning(
                        "Redownloading {}! Size was {} and not {}!".format(
                            filename, out_size, in_size))
                else:
                    # Skip existing file
                    RealtimeLogger.info("Skipped {}".format(filename))
                    return
            
            # Make a temp file
            (handle, path) = tempfile.mkstemp(dir=job.fileStore.getLocalTempDir())
            os.close(handle)        
            
            RealtimeLogger.debug("Download {}".format(filename))
            
            # Download
            in_store.read_input_file(filename, path)
            # Store
            out_store.write_output_file(path, filename)
            
            # Clean up
            os.unlink(path)
            
        except:
            # Put all exception text into an exception and raise that
            raise Exception("".join(traceback.format_exception(
                *sys.exc_info())))
                
        RealtimeLogger.info("Copied {}".format(filename))
        
    # Run all the downloads in parallel
    pool.map(download, batch)
    
        
def main(args):
    """
    Parses command line arguments and do the work of the program.
    "args" specifies the program arguments, with args[0] being the executable
    name. The return value should be used as the program's exit code.
    """
    
    if len(args) == 2 and args[1] == "--test":
        # Run the tests
        return doctest.testmod(optionflags=doctest.NORMALIZE_WHITESPACE)
    
    options = parse_args(args) # This holds the nicely-parsed options object
    
    # Make a root job
    root_job = Job.wrapJobFn(copy_everything, options,
        cores=1, memory="1G", disk="4G")
    
    # Run it and see how many jobs fail
    failed_jobs = Job.Runner.startToil(root_job,  options)
    
    if failed_jobs > 0:
        raise Exception("{} jobs failed!".format(failed_jobs))
        
    print("All jobs completed successfully")
    
    return 0
    
def entrypoint():
    """
    0-argument entry point for setuptools to call.
    """
    
    # Provide main with its arguments and handle exit codes
    sys.exit(main(sys.argv))
    
if __name__ == "__main__" :
    entrypoint()
        
        
        
        
        
        
        
        
        
        

