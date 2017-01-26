# todocopy

Todo Copy is a single-file Python app for batch execution of commands. For example, TC can dump a SQL database, zip that file and other files in a specified source path, and then send everything to an FTP site. Batch files are XML-based.

Execute at the command line with this syntax to see execution examples:

> python todocopy.py examples

## Todo Copy Project Goals

The goals of the Todo Copy project are:

*   Single file -- Most batch and build systems require many files and dependencies. The plan is to make sure TC is only one file, so it can be easily uploaded, included with distributions, and run without installation.
*   Command line and library options -- All library functions (such as PySVN) will also have the SVN command-line equivalents. That way a system that doesn't have the library installed will still have the functions available.
*   Includes all basic batch operations -- Allows scripting of all popular batch operations including file copy, zip, transfer (FTP, SCP, etc.), remote control of other systems with SSH, full knowledge of SVN, CVS, MySQL, and other programs.

## Current features

*   Copy files and directories with ignore list
*   Copy (or FTP) files from a newline-delimited text file list with auto directory create
*   Database summary -- Renders an XML file of the database schema, row count, and data checksum. Great for diff-ing 2 or more databases. Also includes functions to include only specific tables, exclude specific tables, and set a pause between table checksum calculation so it can be used on production server without monopolizing resources.
*   Batch execution sequential commands with Ant-like XML format
*   MySQL options including dump database, dump stored procedure, statement execution
*   Tag substitution -- Tag substitution in parameters and filename (i.e. MyDailyBU_{DATE}_{TIME} -> MyDailyBU_092008_1307)
*   Property setting -- set parameters once that can be used by subsequent commands (such as set DB host name, password, db name for use by following db commands)
*   Zip archive of specified files from multiple sources
*   Automatic FTP transfer of file or files
*   OS execution of any command
*   Email capabilities -- sendmail and SMTP
*   Smart reporting -- Set the reporting level for 0 -- no reporting, 3 -- specified reporting frequency (i.e. 1 out of every 40 messages), and 9 -- all reports
*   Logging -- to screen or file
*   crontab output -- Specify human readable parameters (month=6, day=Thu) and crontab string will be output
*   Recursive svn log and file report -- Recursively search a specified directory and report all logs given critertia (such as between revisions 100:150 or dates). Also displays list of all files changed for this period.
*   Targets -- A script may now have multiple targets. A target may use the execbefore/depends and execafter attributes to call other targets.


# Project Information

*   License: [GNU Lesser GPL](http://www.gnu.org/licenses/lgpl.html)

