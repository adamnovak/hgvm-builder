#!/usr/bin/env python
# hgvm-builder build.py: Command-line tool to build a Human Genome Variation Map
"""

Takes a GRC-format assembly strucutre, and a VCF, and produces a vg graph of the
assembly (including novel and fix patches, alternate loci, and
unlocalized/poorly localized scaffonds) including the variation from the VCF.

Parallelizes using the Toil system.

Requires the "vg" binary to be available on the PATH on all nodes, or provided
in a static build usable by all Toil nodes at a URL.

"""

import argparse
import logging
import os
import os.path
import sys

from toil.job import Job
from toil.realtimeLogger import RealtimeLogger

from .plan import ReferencePlan
from . import grcparser
from . import thousandgenomesparser

# Get a submodule-global logger
Logger = logging.getLogger("build")

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
    parser.add_argument("--assembly_url",
        default=("ftp://ftp.ncbi.nlm.nih.gov/genomes/all/"
        "GCA_000001405.24_GRCh38.p9/"
        "GCA_000001405.24_GRCh38.p9_assembly_structure"),
        help="root of input assembly structure in GRC format")
    parser.add_argument("--vcfs_url", default=("ftp://ftp.1000genomes.ebi.ac.uk/"
        "vol1/ftp/release/20130502/supporting/GRCh38_positions"),
        help="directory of VCFs per chromosome") 
    
    # The command line arguments start with the program name, which we don't
    # want to treat as an argument for argparse. So we remove it.
    args = args[1:]
        
    return parser.parse_args(args)
   
def create_plan(assembly_url, vcfs_url):
    """
    Given an FTP or file url to the root of a GRC-format assembly_structure
    directory tree, and an FTP or file URL to a directory of chrXXX VCFs,
    produce a ReferencePlan describing that assembly and those VCFs.
    """
    
    # Make the plan
    plan = ReferencePlan()

    # Parse the assembly and populate the plan    
    grcparser.parse(plan, assembly_url)
    
    # Parse the VCF directory and add the VCFs
    thousandgenomesparser.parse(plan, vcfs_url)
    
    # Return the completed plan
    return plan
    
def main_job(job, options, plan):
    """
    Root Toil job. Right now does nothing.
    """
    # TODO: implement
    pass
   
def main(args):
    """
    Parses command line arguments and do the work of the program.
    "args" specifies the program arguments, with args[0] being the executable
    name. The return value should be used as the program's exit code.
    """
    
    options = parse_args(args) # This holds the nicely-parsed options object
    
    # Set up logging
    logging.basicConfig(level=logging.INFO)
    
    # Build the plan on the head node
    plan = create_plan(options.assembly_url, options.vcfs_url)
    
    return 1
    
    # Make a root job
    root_job = Job.wrapJobFn(main_job, options, plan,
        cores=1, memory="1G", disk="1G")
    
    # Run it and see how many jobs fail. Automatically handles RealtimeLogger
    # messages
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
        
        
        
        
        
        
        
        
        
        
