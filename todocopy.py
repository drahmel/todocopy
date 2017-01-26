#!/usr/bin/env python
# Todo Copy V1.4 by Dan Rahmel
# (c) Copyright 2007-2017 by Dan Rahmel
# Created December 21, 2007

# Todo Copy can be controlled either by direct commands or through an XML-based batch file.
# If no parameters are given when it is executed, it will look for the batch file tc_autorun.xml
# and execute the script items inside there.
# Sample usage:
# python todocopy.py
# python todocopy.py example_exec.xml
# python todocopy.py example_exec.xml target1
# python todocopy.py copy ./ ../yhw_production			# Copy files from -> to
# python todocopy.py copylist filelist.txt ../yhw_production	# Copy all files in list with automatic path creation
# python todocopy.py -l filelist.txt --ftp 127.127.10.199	# FTP
# python todocopy.py dbsummary  -o dbsumm.xml			# Generate database summary and output to .xml file
# python todocopy.py dbsummary tbvenue,tbtasktype -o db.xml	# Generate database summary of 2 tables and output to .xml file


import os, sys, zlib, zipfile, time, dircache, re, datetime, calendar
from optparse import OptionParser
from time import strftime
import xml.dom.minidom

imports = {}
# Import optional libraries
try:
    import ftplib
    imports['ftp']=True
except:
    pass

try:
    import shutil
    imports['shutil']=True
except:
    pass

try:
    import MySQLdb
    imports['mysql']=True
except:
    pass

try:
    import smtplib
    import email, email.MIMEBase, email.MIMEText, email.MIMEMultipart
    imports['smtp']=True
except:
    pass

try:
    import md5
    imports['md5']=True
except:
    pass

try:
    import sha
    imports['sha1']=True
except:
    pass


class todocopy:
    "Todo Copy will copy, zip,and FTP file backups. It can be commanded directly or through a batch file."
    archivePath =""
    archiveName = ""
    curArchiveName = ""
    curZip = None
    curZipInc = 0
    ignoreSVN = True
    exclusionList = ("jpg","ppt","gif","mov","avi","mp3","swf")
    archiveList = []
    examples = []
    cmdOptions = None
    cmdArgs = None
    curSpaces = "  "
    testMode = False
    reportLevel = 2
    reportSampleInc = 0
    reportSampleFreq = 8
    props={'ignoresvndir':1,'noarchive':0,'srcPath':'','destPath':'','archiveFile':'',
             'reportLevel':2,'reportSampleInc':0,'reportSampleFreq':8,'quietmode':0,
             'db_host':'localhost','db_username':'root','db_password':'', 'db_name':'mysql','db_port':3306,
             'profile_begin_id':0
             }
    tags={}
    commandList = {}
    fileLists = {}
    targetList = {}
    basePath = ""
    reportInc = 0
    mysqlconn = None

    def __init__(self):
        self.data = []
        self.processors = []
        self.returnStr = ""
        self.ignoreSVN = True
        self.tags['DATE'] = strftime("%m%d%y")
        self.tags['TIME'] = strftime("%H%M")
        curMonth = 5
        curYear = 2009
        self.tags['FIRSTDAY'] = self.firstDay(curMonth,curYear)
        self.tags['LASTDAY'] = self.lastDay(curMonth,curYear)
        self.tags['COUNTER'] = 0
        if self.curOS()=='linux':
            self.tags['COLOR_RED'] = '\033[0;31m'
            self.tags['COLOR_BLUE'] = '\033[0;34m'
            self.tags['COLOR_GREEN'] = '\033[0;32m'
            self.tags['COLOR_YELLOW'] = '\033[0;33m'
            self.tags['COLOR_END'] = '\033[m'
        else:
            self.tags['COLOR_RED'] = ''
            self.tags['COLOR_BLUE'] = ''
            self.tags['COLOR_GREEN'] = ''
            self.tags['COLOR_YELLOW'] = ''
            self.tags['COLOR_END'] = ''


    # Get the current revision for output header
    def getRev(self):
        revStr= "$Rev: 62 $"
        tempArray = revStr.split()
        return "1.3."+str(tempArray[1])

    # Replace {tag} items in specified string
    def replaceTags(self,outStr):
        for key, value in self.tags.iteritems():
            outStr = outStr.replace("{" + key + "}", str(value));
        return outStr

    # Test the passed file to see if the three letter file extension is in the exclusion list
    def testExtension(self,inFile):
        return inFile[-3:].lower() in self.exclusionList

    # For status output, all messages are passed here and then based on user preferences,
    # different levels of output are used.
    def report(self,inStr,inInc=0):
        self.reportInc += inInc
        # 0 = Report all
        if self.reportLevel<1:
            print inStr
        # 1 = Report most
        elif self.reportLevel<2:
            print inStr
        # 2 = Report sample
        elif self.reportLevel<3:
            if self.reportSampleInc % int(self.props['reportSampleFreq']) == 0:
                print "\n#"+str(self.reportInc)+":sample: " + inStr
            else:
                print ".",
            self.reportSampleInc += 1
        # 3 = Report status marker
        elif self.reportLevel<4:
            print ".",
        # 4 = Report most
        elif self.reportLevel<5:
            print inStr
    def relativePath(self,basePath,srcPath):
        outPath = srcPath
        bpLen = len(self.basePath)
        if bpLen>0:
            # If paths are the same, remove base path
            if os.path.abspath(srcPath[0:bpLen])==os.path.abspath(basePath):
                # Shave off the preceding slash
                if srcPath[bpLen:bpLen+1] == '/' or srcPath[bpLen:bpLen+1] == '\\':
                    bpLen += 1
                return srcPath[bpLen:]
        return srcPath

    def copyFile(self, inPath,destPath):
        success = False
        (srcPath,fileName) = os.path.split(inPath)
        outPath = os.path.join(destPath,srcPath)
        bpLen = len(self.basePath)
        if bpLen>0:
            # If paths are the same, remove base path
            if os.path.abspath(srcPath[0:bpLen])==os.path.abspath(self.basePath):
                outPath = os.path.join(destPath,srcPath[bpLen:])

        src = os.path.join(srcPath,fileName)
        dest = os.path.join(destPath,srcPath,fileName)
        self.report("Copying file:" + src+ " to: "+dest)
        try:
            if not os.path.isdir(outPath):
                os.makedirs(outPath)
            shutil.copyfile(src,os.path.join(outPath,fileName))
            success = True
        except (IOError, os.error), why:
            print "Can't copy %s to %s: %s" % (src, dest, str(why))
        return success


    # Create XML-based manifest of files to backup with CRC32 checksums
    def createManifest(self,compareManifestName=None):
        # If a manifest name was passed, use it for comparison
        if compareManifestName:
            pass
    def ftpSendFile(self,inFtpRef,inFileName):
        success = False
        myFile = open(inFileName,'rb')
        (fName,fExt) = os.path.splitext(inFileName)
        try:
            inFtpRef.storbinary("STOR " + inFileName,myFile)
            success = True
        except Exception:
            print "Upload failed!"
        myFile.close()
        return success

    def ftpConnect(self,inURL,inUsername,inPassword):
        #   "anonymous" "Anonymous" "anonymous" "Anonymous":
        ftph = ftplib.FTP(inURL)
        ftph.login(inUsername,inPassword)
        print ftph.getwelcome()
        ftph.cwd("bu")
        curFtpPath = ftph.pwd()
        print "Current path:"+curFtpPath
        return ftph
        # ftph.mkd(mkdirname)
        #upload(ftph,lf)
        #ftph.close()
        #ftph = FTP(host_name)
        #ftph.login(user,pwd)
        #ftph.cwd(rmdirname)
        #allfiles = ftph.nlst()
        # print ftph.dir()

    # Get the manifest on the remote directory
    def ftpGetManifest(self):
        pass
    def ftpArchiveList(self,inList,ftpURL,username,password):
        connectPtr = self.ftpConnect(ftpURL,username,password)
        #for arc in inList:
        (head, tail) = os.path.split(inList)
        print "Sending "+tail+"...\n"
        # TODO: The FTP chokes on full paths, so the tail is being used. This is a prob for the crontab though
        self.ftpSendFile(connectPtr,tail)
        print "Completed ftp."
    def doExec(self,cmdStr,asArray=True,standardError=True):
        cmdStr = self.replaceTags(cmdStr)
        rows = []
        outStr = ''
        if standardError:
            cmdStr +=  " 2>&1"
        myProcess  = os.popen(cmdStr)
        for row in myProcess.readlines():     # run find command
            if asArray:
                rows.append(row)
            else:
                outStr += row
        exitStatus = myProcess.close()
        # Check if error occurred
        if exitStatus:
            outStr = "Error:"+outStr
            rows.insert(0,"\n*** Error: ***\n")
        else:
            pass
        if asArray:
            return rows
        else:
            return outStr
    def attr(self,attrList,attrName,default=''):
        if attrList.has_key(attrName):
            return attrList[attrName]
        else:
            return default
    def addExample(self,cmdName,example,desc):
        self.examples.append({'name':cmdName,'example':example,'desc':desc})
    def curOS(self):
        if sys.platform == "darwin":
            return 'mac'
        elif sys.platform == "win32":
            return 'win'
        elif sys.platform.find("linux") != -1:
            return 'linux'
        else:
            return 'linux'
    def getFileList(self,listPath):
        try:
            f=open(listPath, 'r')
            fileList = f.read()
            f.close()
        except (IOError, os.error), why:
            print "Can't read filelist(%s): %s" % (inArgs[0], str(why))
            return None
        return fileList.split("\n")

        def firstDay(self,inMonth,inYear):
                tempDay=datetime.date(inYear,inMonth,1)
                return tempDay.strftime("%Y-%m-%d")
        def lastDay(self,inMonth,inYear):
                monthInfo=calendar.monthrange(inYear,inMonth)
                tempDay=datetime.date(inYear,inMonth,monthInfo[1])
                return tempDay.strftime("%Y-%m-%d")



# -------------  TASKS  -------------
# These tasks can be included in a batch file and perform specific operations

    def taskFindAbove(self,inAttr):
        basePath = inAttr.get('src','')
        fileName= inAttr.get('filename','')
        if len(basePath)==0:
            basePath = os.getcwd()
        curPath = os.path.abspath(basePath)
        for i in range(10):
            testPath = os.path.join(curPath,fileName)
            if os.path.isfile(testPath):
                print "Found at:"+testPath
                return curPath
            else:
                curPath = os.path.abspath(os.path.join(curPath,'../'))
                if(not os.path.isdir(curPath)):
                    break
        print "Can't find file:"+fileName
        return ''


    def taskJoomla(self,inAttr):
        action = inAttr.get('action','')
        if action == 'getconfig':
            configPath = inAttr.get('src','')
            if len(configPath)==0:
                # search for config in current directory and then 10 relative paths up
                configPath = self.taskFindAbove({'src':'./','filename':'configuration.php'})
                if len(configPath)>0:
                    configPath = os.path.join(configPath,'configuration.php')
            if len(configPath)>0:
                print configPath
                f = open(configPath,'r')
                configText = f.read()
                f.close()
                configText = configText.replace('var ','')
                configArray = configText.split("\n")
                joomlaVars = {}
                for entry in configArray:
                    tempVar = entry.split('=')
                    if(len(tempVar)==2):
                        keyName = tempVar[0].replace('$','').strip()
                        tempValue = tempVar[1].replace('"','').replace("'",'').replace(";",'').strip()
                        joomlaVars[keyName] = tempValue
                #print joomlaVars
                if 'host' in joomlaVars:
                    self.props['db_host'] =  joomlaVars['host']
                if 'db' in joomlaVars:
                    self.props['db_name'] = joomlaVars['db']
                if 'user' in joomlaVars:
                    self.props['db_username'] = joomlaVars['user']
                if 'password' in joomlaVars:
                    self.props['db_password'] = joomlaVars['password']
                if len(joomlaVars)>0:
                    print "Found and processed Joomla configuration file."
            else:
                print "The Joomla configuration.php file is not found."
            return



    def taskExamples(self,inArgs):
        print "\n--------- Todo Copy Command Line Examples --------- \n"
        print 'CmdName'.ljust(15)+'Example'.ljust(55)+'Description'
        print '-------'.ljust(15)+'-------'.ljust(55)+'-----------'
        for example in self.examples:
            print example['name'].ljust(15)+example['example'].ljust(55)+example['desc']

    def taskSHA1(self,inAttr):
        if 'sha1' in imports:
            plaintext = inAttr.get('source','')
            encoderSHA1 = sha.new()
            encoderSHA1.update(plaintext)
            print plaintext+' = '+encoderSHA1.hexdigest()
        else:
            print "Missing SHA1 encoding library"

    def taskMD5(self,inAttr):
        if 'md5' in imports:
            plaintext = inAttr.get('source','')
            encoderMD5 = md5.new()
            encoderMD5.update(plaintext)
            print plaintext+' = '+encoderMD5.hexdigest()
        else:
            print "Missing MD5 encoding library"

    def taskSetPath(self,inPath):
        myOS = self.curOS()
        if myOS == 'win':
            pathCmd = "set PATH=%PATH%;"+os.path.join(os.getcwd())
            #print pathCmd
            print sys.path
            sys.path.append(os.getcwd())
            print sys.path
            #os.system(pathCmd)
            #print self.doExec(pathCmd,False)
        elif myOS == 'linux':
            pass
        elif myOS == 'mac':
            pass

    def taskCreateList(self,inArgs):
        srcDir = inArgs['src']
        destDir = inArgs['dest']
        self.basePath = srcDir
        recurse = self.props.get('recursive',0)
        dirList = []
        fileList = []
        i = 0
        if recurse:
            for curPath,dirs,files in os.walk(srcDir):
                for inName in files:
                    fileList.append(self.relativePath(srcDir,os.path.join(curPath,inName)))
                    i += 1
                if self.ignoreSVN:
                    if '.svn' in dirs:
                        dirs.remove('.svn')  # ignore the SVN metadata directories
                for inName in dirs:
                    tempDirPath = self.relativePath(srcDir,os.path.join(curPath,inName))
                    tempDirPath += os.sep
                    dirList.append(tempDirPath)

            #walkLog.close()
        else:
            fileList = os.listdir(srcDir)
            # Copy the return value so we can change 'fileList'
            fileList = fileList[:]
            # Remove SVN
            if fileList[0]=='.svn' and self.ignoreSVN:
                del fileList[0]
            # Add trailing '/' if item is a directory
            dircache.annotate(os.sep, fileList)

        if len(destDir)> 0:
            if(destDir[:1]=='['):
                print "Setting property:"+destDir[1:-1]
            else:
                outputType = inArgs.get('type','newline')
                if outputType == 'newline':
                    f = open(destDir,'w')
                    f.write("\n".join(dirList))
                    f.write("\n".join(fileList))
                    f.close()
                elif outputType =='comma':
                    import csv
                    writer = csv.writer(open(destDir, "wb"))
                    writer.writerows([dirList,fileList])

                print "File list output complete to:"+destDir
        else:
            print "\n".join(dirList)
            print "\n".join(fileList)

    def taskCopy(self,inArgs):
        #def copyFiles(self,srcDir,destDir,
        recurse=True
        inLog=False
        srcDir = inArgs['src']
        destDir = inArgs['dest']
        #print srcDir, destDir
        self.returnStr = ""
        self.ignoreSVN = True
        self.basePath = srcDir
        i = 0
        #walkLog=open(walkDir+'codescan_log.txt', 'w')
        if recurse:
            for curPath,dirs,files in os.walk(srcDir):
                for inName in files:
                    #if inName[-3:] == "php":
                    #	processFile(inName,curPath,walkLog)
                    #print "Copy file:"+curPath+"/"+inName+" to "+destDir+curPath+"/"+inName
                    self.copyFile(os.path.join(curPath,inName),destDir)
                    i += 1
                if self.ignoreSVN:
                    if '.svn' in dirs:
                        dirs.remove('.svn')  # ignore the SVN metadata directories
            #walkLog.close()
        if i>1:
            print "\nCopied "+str(i)+" files"
        return True

    def taskCopyList(self,inArgs):
        fileList = self.getFileList(inArgs['filelist'])
        if fileList:
            i = 0
            for curFile in fileList:
                if(len(curFile)>0):
                    if self.copyFile(curFile, inArgs['dest']):
                        i += 1
            self.report("Copied "+str(i)+" files.")

    def taskFTPList(self,inArgs):
        fileList = self.getFileList(inArgs['filelist'])
        if fileList:
            # TODO: Add FTP connection
            i = 0
            for curFile in fileList:
                if(len(curFile)>0):
                    (head, tail) = os.path.split(curFile)
                    self.report("Sending "+tail+"...\n")
                    # TODO: The FTP chokes on full paths, so the tail is being used. This is a prob for the crontab though
                    if self.ftpSendFile(connectPtr,tail):
                        i += 1
            self.report("FTPed "+str(i)+" files.")

    def taskExec(self,inAttr):
        if inAttr:
            cmdStr = ''
            if inAttr.has_key('value'):
                cmdStr = inAttr['value'].value
            if inAttr.has_key('executable'):
                cmdStr = inAttr['executable'].value
            returnArray = self.doExec(cmdStr)
            print ''.join(returnArray)

    def taskSVNDirList(self,inAttr):
        if self.cmdOptions.recursive:
            recurse = 1
        else:
            recurse = inAttr.get('recurse', 0)
        recurseStr = ''
        if recurse:
            recurseStr = ' -R '
        revStr = inAttr.get('revstr', '')
        if self.cmdOptions.source:
            srcDir = self.cmdOptions.source
        else:
            srcDir = inAttr.get('src', ' . ')
        svnDirs = []
        svnFiles = []
        cmdStr = "svn info "+recurseStr+' '+srcDir+" --xml"
        print cmdStr
        xmlStr = self.doExec(cmdStr,False)
        if xmlStr[:6] == "Error:":
            endError = xmlStr.find("\n")
            print xmlStr[:endError]
            return
        svnDOM = xml.dom.minidom.parseString(xmlStr)
        targets = svnDOM.getElementsByTagName("info").item(0).childNodes
        # Find all the files and directories in this working copy tree
        print "Beginning svn folder recurse..."
        for target in targets:
            elementName = target.localName
            if elementName == 'entry':
                entryKind = target.getAttribute('kind')
                if entryKind == 'dir':
                    urlNode = target.getElementsByTagName("url")
                    svnDirs.append(urlNode.item(0).childNodes.item(0).nodeValue)
                    print ".",
                elif entryKind == 'file':
                    urlNode = target.getElementsByTagName("url")
                    svnFiles.append(urlNode.item(0).childNodes.item(0).nodeValue)
        print "Total svn dirs:"+str(len(svnDirs))
        return svnDirs
    def taskSVNFindReplaceProp(self,inAttr):
        myDirs = self.taskSVNDirList(self,inAttr)
        # Look through directories
        for myDir in myDirs:
            print myDir
            propGetStr = "svn propget "+myDir
            # returnArray = self.doExec(propGetStr)

    def taskSVN(self,inAttr):
        # TODO: Process return info as XML and report specific items.
        action = inAttr.get('action', '')
        if action=='status':
            cmdStr = "svn status -u --xml"
            xmlStr = self.doExec(cmdStr,False)
            svnDOM = xml.dom.minidom.parseString(xmlStr)
            entries = svnDOM.getElementsByTagName("target").item(0).childNodes
            modFiles = []
            for entry in entries:
                elementName = entry.localName
                if elementName == 'entry':
                    status = ''
                    repoElement = entry.getElementsByTagName("repos-status")
                    if repoElement:
                        status = repoElement.item(0).getAttribute('item')
                    if status == 'modified':
                        modFiles.append(entry.getAttribute('path'))
            if len(modFiles)>0:
                print "\n____ Modified Files in Repository ____"
                for fileName in modFiles:
                    print fileName
            #print xmlStr # ''.join(returnArray)
        # Sync will revert all modified files, remove non-versioned files and (empty) dirs, and do an SVN UP
        # This is perfect for a moving files from a dev checkout to a production checkout
        elif action=='sync':
            cmdStr = "svn revert . -R"
            returnArray = self.doExec(cmdStr)
            print ''.join(returnArray)
            cmdStr = "svn status --xml"
            returnArray = self.doExec(cmdStr)
            #print ''.join(returnArray)
            xmlStr = ''.join(returnArray)
            svnDOM = xml.dom.minidom.parseString(xmlStr)
            targets = svnDOM.getElementsByTagName("target").item(0).childNodes
            for target in targets:
                elementName = target.localName
                if elementName == 'entry':
                    status = target.getElementsByTagName("wc-status").item(0).getAttribute('item')
                    if status == 'unversioned':
                        delPath = target.getAttribute('path')
                        print "Deleting:" + delPath
                        if os.path.isdir(delPath):
                            try:
                                os.rmdir(delPath)
                            except (IOError, os.error), why:
                                print "Can't delete %s: %s" % (delPath,str(why))
                        else:
                            os.remove(delPath)
            cmdStr = "svn up"
            returnArray = self.doExec(cmdStr)
            print ''.join(returnArray)
        elif action=='property':
            filePath = inAttr.get('path', '')
            propName = inAttr.get('name', '')
            # If there is a value, then it's a set, otherwise a get
            if 'value' in inAttr:
                propVal = inAttr.get('value', '')
                # If property has newline characters, SVN won't honor them from the command line,
                # so they need to be written to a temp file which does work
                if propVal.find("\\n") != -1:
                    propVal = propVal.replace("\\n","\n")
                    tempFilename = 'tempSVNPropSet.txt'
                    # Write property value to the temp file
                    f = open(tempFilename,'w')
                    f.write(propVal)
                    f.close()
                    cmdStr = "svn propset "+propName+" -F "+tempFilename+" "+filePath
                    returnArray = self.doExec(cmdStr)
                    os.remove(tempFilename)
                else:
                    cmdStr = "svn propset "+propName+' "'+propVal+'" '+filePath
                    print cmdStr
                    returnArray = self.doExec(cmdStr)
                print ''.join(returnArray)
            else:
                print "Get "+propName
        elif action=='dir':
            self.taskSVNDirList(inAttr)
        elif action=='findreplaceprop':
            self.taskSVNFindReplaceProp(inAttr)
        elif action=='add':
            filePath = inAttr.get('path', '')
            if filePath:
                cmdStr = "svn add "+filePath
                print cmdStr
                returnArray = self.doExec(cmdStr)
                print ''.join(returnArray)

        elif action=='log':
            recurse = inAttr.get('recurse', 0)
            recurseStr = ''
            if recurse:
                recurseStr = ' -R '
            revStr = inAttr.get('revstr', '')
            srcDir = inAttr.get('src', ' . ')
            svnDirs = []
            svnFiles = []
            cmdStr = "svn info "+recurseStr+' '+srcDir+" --xml"
            xmlStr = self.doExec(cmdStr,False)
            svnDOM = xml.dom.minidom.parseString(xmlStr)
            targets = svnDOM.getElementsByTagName("info").item(0).childNodes
            # Find all the files and directories in this working copy tree
            print "Beginning svn folder recurse..."
            for target in targets:
                elementName = target.localName
                if elementName == 'entry':
                    entryKind = target.getAttribute('kind')
                    if entryKind == 'dir':
                        urlNode = target.getElementsByTagName("url")
                        svnDirs.append(urlNode.item(0).childNodes.item(0).nodeValue)
                        print ".",
                    elif entryKind == 'file':
                        urlNode = target.getElementsByTagName("url")
                        svnFiles.append(urlNode.item(0).childNodes.item(0).nodeValue)
            print "Total svn dirs:"+str(len(svnDirs))
            # Output the logs for all the directories
            logArray = []
            for curDir in svnDirs:
                # print curDir,len(curDir)
                cmdStr = "svn log "+revStr+" " +curDir+ " --xml --verbose "
                xmlStr = self.doExec(cmdStr,False)
                if xmlStr[0:len("Error:")] != "Error:":
                    logArray.append(xmlStr)
            print "Logs:"+str(len(logArray))
            revMessages = {}
            totalPaths = {}
            # Parse the logs to find the messages
            for xmlStr in logArray:
                svnDOM = xml.dom.minidom.parseString(xmlStr)
                targets = svnDOM.getElementsByTagName("log").item(0).childNodes
                for target in targets:
                    elementName = target.localName
                    if elementName == 'logentry':
                        entryRev = target.getAttribute('revision')
                        logDate = target.getElementsByTagName("date").item(0).childNodes.item(0).nodeValue
                        msg = target.getElementsByTagName("msg").item(0).childNodes.item(0).nodeValue
                        # Only add if revision has not already been logged
                        if entryRev not in revMessages:
                            logPathArray = []
                            # Get the list of path elements
                            pathTargets = target.getElementsByTagName("paths").item(0).childNodes
                            for pathItem in pathTargets:
                                elementName = pathItem.localName
                                if elementName == 'path':
                                    logPathArray.append(pathItem.childNodes.item(0).nodeValue)
                            revMessages[entryRev] = {'date':logDate,'msg':msg,'paths':logPathArray}
                            for mypath in logPathArray:
                                                if mypath not in totalPaths:
                                    totalPaths[mypath] = 1
            #print revMessages
            print "___________ Logs ___________"
            revKeys = revMessages.keys()
            revKeys.sort()
            tb = "\t"
            for revEntry in revKeys:
                print 'Rev:'+revEntry+tb+revMessages[revEntry]['date']+tb+revMessages[revEntry]['msg']+tb+'Files:'+','.join(revMessages[revEntry]['paths'])
            print "___________ Files Changed ___________"
            pathList = totalPaths.keys()
            pathList.sort()
            for mypath in pathList:
                print mypath

    # Output a crontab string from human-readable batch input
    def taskCrontab(self,inAttr):
        crCmd = inAttr.get('cmd', '/etc/myprog')
        crOutfile = inAttr.get('log', '')
        if len(crOutfile)>0:
            crOutfile = " > "+crOutfile
        crMonth = inAttr.get('month', '*')
        crDay = inAttr.get('day', '*')
        crHour = inAttr.get('hour', '*')
        crMin = inAttr.get('min', '*')
        dow = inAttr.get('dayofweek').lower()
        dowNum = '*'
        if(dow=='sunday' or dow=='sun'):
            dowNum='0'
        elif(dow=='monday' or dow=='mon'):
            dowNum='1'
        elif(dow=='tuesday' or dow=='tue'):
            dowNum='2'
        elif(dow=='wednesday' or dow=='wed'):
            dowNum='3'
        elif(dow=='thursday' or dow=='thu'):
            dowNum='4'
        elif(dow=='friday' or dow=='fri'):
            dowNum='5'
        elif(dow=='saturday' or dow=='sat'):
            dowNum='6'
        print "crontab string: "+crMin+" "+crHour+" "+crDay+" "+crMonth+" "+dowNum+" "+crCmd+" "+crOutfile
    def taskEmail(self,inAttr):
        print "Sending email."
        # TODO: Check OS type property
        emailMethod = inAttr.get('method', 'smtp')
        emailFrom = inAttr.get('from', 'todocopy@example.com')
        emailTo = inAttr.get('to', 'danr@example.com')
        emailSubject = inAttr.get('subject', 'Todo Copy test {DATE}')
        emailSubject = self.replaceTags(emailSubject)
        emailBody = inAttr.get('body', "The SC Body\nSome more text.\n")
        emailBody = self.replaceTags(emailBody)
        emailAttachments = inAttr.get('attach', "")

        if emailMethod=='sendmail':
            cmdSendMail = "/usr/sbin/sendmail"
            p = os.popen("%s -t -v " % cmdSendMail, "w")
            p.write("To: "+emailTo+"\n")
            p.write("From: "+emailFrom+"\n")
            p.write("Subject: "+emailSubject+"\n")
            p.write("\n")
            p.write(emailBody)
            sts = p.close()
            if sts != 0:
                print "Sendmail exit status", sts
        else:
            server = smtplib.SMTP('localhost')
            msg = email.MIMEMultipart.MIMEMultipart()
            msg['From'] = emailFrom
            msg['To'] = emailTo
            msg['Date'] = email.Utils.formatdate(localtime=True)
            msg['Subject'] = emailSubject

            msg.attach(email.MIMEText.MIMEText(emailBody))

            attachments = emailAttachments.split(",")
            for attachment in attachments:
                attach = attachment.strip()
                if len(attach)>0:
                    part = email.MIMEBase.MIMEBase('application', "octet-stream")
                    part.set_payload(open(attach,"rb").read())
                    email.Encoders.encode_base64(part)
                    part.add_header('Content-Disposition', 'attachment; filename="%s"' % os.path.basename(attach))
                    msg.attach(part)

            server.sendmail(emailFrom, emailTo.split(","), msg.as_string())
            server.quit()

    # Output a crontab string from human-readable batch input
    def taskWorkingDir(self,inAttr):
        chPath = os.path.abspath(inAttr.get('value', ''))
        try:
            os.chdir(chPath)
            self.report("Changed to directory:"+chPath)
        except (IOError, os.error), why:
            print "Can't change to directory %s: %s" % (delPath,str(why))

    # Make a directory with sub-directories if necessary
    def taskMkDir(self,inAttr):
        try:
            destPath = os.path.abspath(inAttr.get('value', ''))
            os.makedirs(destPath)
        except (IOError, os.error), why:
            print "Error creating directory: %s -- %s" % ( destPath, str(why))

    def taskDBSummary(self,inAttr):
        if 'mysql' in imports:
            outStr = ""
            try:
                conn = MySQLdb.connect (host = self.props['db_host'], user = self.props['db_username'],passwd = self.props['db_password'], db = self.props['db_name'])
                cursor = conn.cursor()
            except MySQLdb.Error, e:
                print "Error %d: %s" % (e.args[0], e.args[1])
                return
            dbname = self.props['db_name']
            try:
                if 'tablelist' not in inAttr:
                    inAttr['tablelist'] = ''
                if 'excludelist' not in inAttr:
                    inAttr['excludelist'] = {}
                else:
                    inAttr['excludelist'] = inAttr['excludelist'].split(",")


                pauseBetween = inAttr.get('pausebetween',0);
                checksum = inAttr.get('checksum',0);
                pauseBetween = inAttr.get('pausebetween',0);
                onlymissing = inAttr.get('onlymissing',0);
                getLenText = int(inAttr.get('getlentext',0));
                textColLog = "textColLog.txt"
                logFile = open(textColLog,'w')
                logFile.write("Table\tColumn\tMax Entry Length\n")
                logFile.close()

                if inAttr['tablelist'] != '':
                    tempTables = inAttr['tablelist'].split(",")
                    tables = []
                    for tempTable in tempTables:
                        tables.append([tempTable,''])
                else:
                    sql = "SHOW TABLES FROM "+dbname
                    cursor.execute(sql)
                    tables = cursor.fetchall()
                outStr += "<?xml version='1.0' encoding='UTF-8' ?>\n"
                outStr += "<database name='"+dbname+"' server='"+self.props['db_host']+"' date='"+strftime("%Y-%m-%d")+"' tables='"+str(len(tables))+"' >\n";
            except MySQLdb.Error, e:
                print "Error %d: %s" % (e.args[0], e.args[1])
                return

            try:
                cursorDict = conn.cursor(MySQLdb.cursors.DictCursor)
                fieldStr = ''
                fieldList = ''
                for table in tables:
                    # If table is listed in the excludelist, skip it
                    if table[0] in inAttr['excludelist']:
                        continue
                    colsCount = 0

                    # Pause between table reads if executing on production server so resources aren't monopolized
                    if pauseBetween:
                        print "(pause)",
                        time.sleep(float(pauseBetween))
                    self.report("Summarizing table:"+table[0],1)
                    sql = "SHOW FIELDS FROM "+table[0]
                    cursorDict.execute(sql)
                    cols = cursorDict.fetchall()
                    # TODO: Create list of fields for CRC routine
                    fieldStr = ''
                    fieldList = ''
                    textMaxList = ''
                    hasPrimaryKey = 0
                    for col in cols:
                        colType = col['Type'].replace("'",'"')
                        if fieldList != '':
                            fieldList += ','
                        fieldList += '`' + str(col['Field']) + '`'
                        colsCount += 1
                        priKey = '0'
                        if col['Key']=="PRI":
                            priKey = '1'
                            hasPrimaryKey = 1
                        fieldStr += "\t\t<field name='"+str(col['Field'])+"' type='"+str(colType)+"' primary='"+priKey+"' null='"+str(col['Null'])+"' key='"+str(col['Key'])+"' default='"+str(col['Default'])+"' extra='"+str(col['Extra'])+"' />\n"
                        if str(colType)=='text' and getLenText==1:
                            sql = "select max(length(`"+str(col['Field'])+"`)) as maxlen FROM "+table[0]
                            try:
                                cursorDict.execute(sql)
                                maxlen = cursorDict.fetchall()
                            except:
                                print "Failed with query:"+sql
                            try:
                                textMaxList += "\t"+str(col['Field'])+"\t"+str(maxlen[0]['maxlen'])+"\n"
                            except:
                                pass
                            #print "Text field: "+str(col['Field'])+" Max Entry Length: "+str(maxlen[0]['maxlen'])
                    if len(textMaxList)>0:
                        logFile = open(textColLog,'a')
                        logFile.write("\n"+table[0]+"\n")
                        logFile.write(textMaxList)
                        logFile.close()
                    sql = "SHOW INDEXES FROM "+table[0]
                    cursorDict.execute(sql)
                    indexes = cursorDict.fetchall()
                    indexStr = ''
                    indexCount = len(indexes)
                    hasPrimaryIndex = 0
                    for curIndex in indexes:
                        if str(curIndex['Key_name']) == 'PRIMARY':
                            hasPrimaryIndex = 1
                        indexStr += "\t\t<index keyname='"+str(curIndex['Key_name'])+"' colname='" +str(curIndex['Column_name'])
                        indexStr += "' collation='"+str(curIndex['Collation'])+"' null='"+str(curIndex['Null'])+"' comment='"+str(curIndex['Comment'])
                        indexStr += "' sequence='"+str(curIndex['Seq_in_index'])+"' non_unique='"+str(curIndex['Non_unique'])+"' />\n";

                    if checksum:
                        tableName = table[0]
                        sql = "set @checksum := '', @rowCount := 0 "
                        cursorDict.execute(sql)
                        sql = "select min(least(length(@checksum := md5(concat( @checksum, md5(concat_ws('|', "+fieldList+" ))))), @rowCount := @rowCount + 1)) as beNull from "+tableName #+" use index(PRIMARY) "
                        try:
                            cursorDict.execute(sql)
                        except:
                            print "\nWarning: Table "+tableName+" has no PRIMARY index\n"
                        sql = "select @checksum crc, @rowCount rows"
                        cursorDict.execute(sql)
                        checksumInfo = cursorDict.fetchall()
                        checksumRows = checksumInfo[0]['rows']
                        checksumVal = checksumInfo[0]['crc']
                    else:
                        checksumRows = '0'
                        checksumVal = ''

                    emptyTable = " empty='0' "
                    if(int(checksumRows)==0):
                        emptyTable = "\n\t\t empty='1' "

                    if (onlymissing and (hasPrimaryKey==0 or hasPrimaryIndex==0 or indexCount==0)) or onlymissing==False:
                        outStr += "\t<table name='"+table[0]+"' rows='"+str(checksumRows)+"' checksum='"+checksumVal+"' cols='"+str(colsCount)+"' "
                        outStr += " indexes='" + str(indexCount) + "' " + "' hasprimarykey='" + str(hasPrimaryKey) + "' hasprimaryindex='" + str(hasPrimaryIndex) + "' "
                        outStr += emptyTable+" >\n";

                        outStr += fieldStr
                        outStr += indexStr
                        outStr += "\t</table>\n" ;


            except MySQLdb.Error, e:
                print "Error %d: %s" % (e.args[0], e.args[1])
                return
            outStr += "\n</database>"
            cursor.close()
            conn.close()
            if self.cmdOptions.outfile or ('output' in inAttr):
                if self.cmdOptions.outfile:
                    outFilename = self.cmdOptions.outfile
                else:
                    outFilename = inAttr['output']
                try:
                    f=open(outFilename,'w')
                    f.write(outStr)
                    f.close()
                except (IOError, os.error), why:
                    print "Can't write to %s: %s" % (outFilename,str(why))

            else:
                print outStr
        else:
            print "DBSummary requires MySQL library to be installed and none found.\nOn RedHat, try 'yum install mysql-python' or 'yum install MySQL-python'\n"

    # Output to screen or files information supplied in <log> tags
    def taskLog(self,inAttr):
        logFile = inAttr.get('output','')
        logFile = self.replaceTags(logFile)
        if len(logFile)>0:
            self.props['logfile'] = logFile
        msg = inAttr.get('msg','')
        if len(msg)>0:
            msg = self.replaceTags(msg)
            includeDate = inAttr.get('date', '')
            toFile = inAttr.get('tofile', '')
            if(toFile=='0'):
                toFile = False
            toScreen = inAttr.get('toscreen', '')
            if(toScreen=='0'):
                toScreen = False
            if(len(logFile)==0):
                logFile = "tc_log.log"
            dateStr = ''
            if includeDate != '0':
                dateStr = strftime("%y%m%d-%H:%M") + "\t"
            logStr = dateStr + msg+"\n"
            if(toFile):
                try:
                    f=open(logFile, 'a')
                    f.write(logStr)
                    f.close()
                except (IOError, os.error), why:
                    print "Can't write %s to %s: %s" % (logStr,logFile,str(why))
            if(toScreen):
                print logStr

    def taskFTP(self,fileList,ftpURL,username,password):
        print "\nStarting ftp to "+ftpURL+"..."
        passList = (fileList)
        self.ftpArchiveList(passList,ftpURL,username,password)
    def taskZip(self,inSrc,inDest,inFile,recurse=True,inLog=False):
        if self.props['noarchive']:
            print "No archiving, just transfer file."
            self.archiveList.append(self.props['noarchive'])
        else:
            if inFile:
                self.curArchiveName = os.path.join(inDest,inFile+"_"+str(self.curZipInc)+".zip")
                self.curZip = zipfile.ZipFile(self.curArchiveName,'w') # ,zipfile.ZIP_DEFLATED
                self.archiveList.append(self.curArchiveName)
            if self.testMode:
                print "zipping:"+inSrc+" recurse:"+str(recurse)+" to:"+self.curArchiveName
            self.processDir(inSrc,recurse,inLog)
            if self.props['archiveFile']:
                self.curZip.close()

    def taskSCP(self,inAttr):
        if sys.platform == "darwin":
            scpName = "scp"
        elif sys.platform == "win32":
            scpName = "pscp"
        elif sys.platform.find("linux") != -1:
            scpName = "scp"
        else:
            scpName = "scp"

        portStr = "10018"
        srcPath = "add_to_favorites.php"
        destUser = "root"
        destURL = "stage.apmmusic.com"
        destPath = "/var/www/html/testapm/myapm/"
        sendStr = scpName + " -P " + portStr + " " + srcPath + " " + destUser + "@" + destURL + ":" + destPath
        print sendStr
        srcPath = "/var/www/html/testapm/myapm/add_to_favorites.php"
        destPath = "add_to_favorites.php"
        receiveStr = scpName + " -P " + portStr + " " + destUser + "@" + destURL + ":" + srcPath + " " + destPath
        print receiveStr

    def mysqlConnect(self):
        try:
            conn = MySQLdb.connect (host = self.props['db_host'], user = self.props['db_username'],passwd = self.props['db_password'], db = self.props['db_name'],port=int(self.props['db_port']))
            self.mysqlconn = conn
            return conn
        except MySQLdb.Error, e:
            print "MySQL Error %d: %s" % (e.args[0], e.args[1])
            return False

    def printRow(self,inRow,fields=None):
        outStr = ''
        for i in fields:
            outStr += str(inRow[i])+"\t"
        return outStr

    # Perform MySQL tasks
    def taskMySQL(self,inAttr=None):
        action = self.props['action']
        if action=='dump':
            # Dump the MySQL database
            self.taskDBDump(inAttr)
        elif action=='import':
            self.taskDBImport(inAttr)
        elif action=='profile':
            # Perform a timing profile of SQL statements
            self.taskDBProfile(inAttr)
        elif action=='query':
            self.taskDBQuery(inAttr)
        elif action=='importfiles':
            # Import a directory full of .sql files and add permissions to specified user
            self.taskDBImportFiles(inAttr)
        elif action=='load':
            print "Loading database:"+self.props['db_name']
            pathMySQL = os.path.join(self.props['path_mysql'],'mysql')
            loadFile = os.path.join('',self.props['srcPath'])
            dbSelect = inAttr.get('db_name','')
            if dbSelect:
                dbSelect = ' -D '+dbSelect

            cmdStr = os.path.normpath(pathMySQL)+" -h "+self.props['db_host']+" -u "+self.props['db_username']+" -p"+self.props['db_password']+" -P"+str(self.props['db_port'])+dbSelect+" < "+loadFile
            #print cmdStr
            returnArray = self.doExec(cmdStr)
            print ''.join(returnArray)


    def taskDBProfile(self,inAttr=None):
        profileAction = inAttr.get('type','')

        if 'mysql' in imports:
            if not self.mysqlconn:
                conn = self.mysqlConnect()
                if conn == False:
                    return False
            else:
                conn = self.mysqlconn
            cursorDict = conn.cursor(MySQLdb.cursors.DictCursor)
            if profileAction == 'begin':
                self.report('Beginning profile...')
                # Clear the caches so the profile execution is accurate
                sql = "RESET QUERY CACHE;"
                cursorDict.execute(sql)
                sql = "FLUSH TABLES;"
                cursorDict.execute(sql)
                try:
                    sql = "SET PROFILING=1;"
                    cursorDict.execute(sql)
                except MySQLdb.Error, e:
                    if e.args[0]==1193:
                        print "\n\nERROR: Could not activate MySQL Profiling system. Profiling requires Community Edition MySQL 5.0.37 or above.\n"
                    else:
                        print "\nMySQL error %d: %s" % (e.args[0], e.args[1])
                    return False
                # Find the last query number already in the profile table
                sql =  "SHOW PROFILES;"
                cursorDict.execute(sql)
                tempResult = cursorDict.fetchall()
                if not len(tempResult):
                    self.props['profile_begin_id'] = 1
                else:
                    self.props['profile_begin_id'] = int(len(tempResult))+1
                self.report("Starting profile at query id:"+str(self.props['profile_begin_id']))
            elif profileAction == 'end':
                if not self.mysqlconn:
                    conn = self.mysqlConnect()
                    if conn == False:
                        return False
                else:
                    conn = self.mysqlconn
                cursorDict = conn.cursor(MySQLdb.cursors.DictCursor)
                try:
                    sql = "SET PROFILING=0;"
                    cursorDict.execute(sql)
                except MySQLdb.Error, e:
                    if e.args[0]==1193:
                        print "\n\nERROR: Could not activate MySQL Profiling system. Profiling requires Community Edition MySQL 5.0.37 or above.\n"
                    else:
                        print "\nMySQL error %d: %s" % (e.args[0], e.args[1])
                    return False

                sql =  "SHOW PROFILES;"
                cursorDict.execute(sql)
                tempResult = cursorDict.fetchall()
                if len(tempResult)>0:
                    queries = []
                    # Get information about each profile
                    for i in range(self.props['profile_begin_id']-1,len(tempResult)):
                        queries.append(tempResult[i])
                    curQuery = tempResult[len(tempResult)-1]['Query_ID']
                    self.props['profile_end_id'] = int(curQuery)

                    # Get itemized profile information
                    for query in queries:
                        sql = "SHOW PROFILE FOR QUERY "+str(query['Query_ID'])
                        cursorDict.execute(sql)
                        tempResult = cursorDict.fetchall()
                        query['items'] = tempResult
                    print 'Profile complete for '+str(len(queries))+' queries.'
                    outStr = ''
                    for query in queries:
                        outStr += "Query: "+query['Query']+"\n"
                        curDuration = 0
                        for entry in query['items']:
                            outStr += "\t"+self.printRow(entry,['Status', 'Duration'])+"\n"
                            curDuration += float(entry['Duration'])
                        outStr += "\t\tQuery total: "+str(curDuration)+"\n"
                    profileFile = inAttr.get('output','profileOut.txt')
                    try:
                        f = open(profileFile,'w')
                        f.write(outStr)
                        f.close()
                    except (IOError, os.error), why:
                        print "Can't copy %s to %s: %s" % (src, dest, str(why))

        else:
            print "need mysql-python"

    def taskDBQuery(self,inAttr=None):
        self.report('Querying: '+self.props['msg'])
        if 'mysql' in imports:
            if not self.mysqlconn:
                try:
                    conn = MySQLdb.connect (host = self.props['db_host'], user = self.props['db_username'],passwd = self.props['db_password'], db = self.props['db_name'])
                    self.mysqlconn = conn
                except MySQLdb.Error, e:
                    print "Error %d: %s" % (e.args[0], e.args[1])
                    return False
            else:
                conn = self.mysqlconn
            cursorDict = conn.cursor(MySQLdb.cursors.DictCursor)
            sql = inAttr.get('query','')
            #print sql
            if len(sql)>0:
                try:
                    cursorDict.execute(sql)
                except MySQLdb.Error, e:
                    print "Error %d: %s" % (e.args[0], e.args[1])
                    return

                tables = cursorDict.fetchall()
                self.report("Number of records:"+str(len(tables)),1)
            else:
                print "Empty query."
        else:
            # No Mysql-Python library, execute from the command line
            rows = []
            pathMySQL = os.path.normpath(os.path.join(self.props['path_mysql'],'mysql'))
            queryCmd = pathMySQL+" -h "+self.props['db_host']+" -u "+self.props['db_username']+" -p"+self.props['db_password']+' --execute="'+self.props['query']+'" '+self.props['db_name']
            for row in os.popen(queryCmd).readlines():     # run find command
                rows.append(row)
            return rows


    def taskDBImportFiles(self,inAttr=None):
        processFiles = inAttr.get('processfiles','0')
        srcPath = self.props['srcPath'];
        print 'MySQL import from '+srcPath+'...'
        fileTotal = 0
        for filename in os.listdir(os.path.abspath(srcPath)):
            path = os.path.join(srcPath, filename)
            if not os.path.isfile(path):
                continue
            if filename[-3:] == "sql":
                fileTotal += 1
                if processFiles=='1' and ('mysql' in imports):
                    sqlFile = os.path.join(os.path.abspath(srcPath),filename)
                    sqlText = ''
                    try:
                        f = open(sqlFile,'r')
                        sqlText = f.read()
                        f.close()
                    except:
                        print "Error opening file:"+sqlFile
                    # Replace all multi-line comments since MySQL often has problems with them
                    sqlText = re.sub("(/\*([^|]*?)\*/)"," ",sqlText)
                    # Replace tags
                    sqlText = self.replaceTags(sqlText)
                    print "processing file:"+sqlFile
                    self.taskDBQuery({'query':sqlText})
                    #print sqlText
                else:
                    os.chdir(os.path.abspath(srcPath))
                    pathMySQL = os.path.normpath(os.path.join(self.props['path_mysql'],'mysql'))
                    importCmd = pathMySQL + " -h " + self.props['db_host'] + " -u " + self.props['db_username'] + " -p" + self.props['db_password'] + " --database=" + self.props['db_name'] + " < " + filename
                    #print importCmd
                    returnArray = self.doExec(importCmd)
                    print ''.join(returnArray)
                    #os.system(importCmd)
                    if filename[0:2] == "sp" or filename[0:2] == "fn":
                        spName = filename[:-4]
                        grantSQL = "GRANT EXECUTE ON PROCEDURE "+self.props['db_name']+"."+spName+" TO '"+self.props['sp_user']+"'@'localhost';"
                        grantCmd = pathMySQL+" -h "+self.props['db_host']+" -u "+self.props['db_username']+" -p"+self.props['db_password']+' --execute="'+grantSQL+'" '
                        os.system(grantCmd)
                        grantSQL = "GRANT EXECUTE ON PROCEDURE "+self.props['db_name']+"."+spName+" TO '"+self.props['sp_user']+"'@'%';"
                        grantCmd = pathMySQL+" -h "+self.props['db_host']+" -u "+self.props['db_username']+" -p"+self.props['db_password']+' --execute="'+grantSQL+'" '
                        os.system(grantCmd)
                    self.report("Import: "+importCmd)


    def  taskDBDump(self,inAttr=None):
        dumpTables = inAttr.get('tables','')
        dumpTables = dumpTables.replace("\n"," ")
        print "Dumping:"+self.props['db_name'] + " " + dumpTables
        pipeDir = ''
        # Set default attributes
        if len(inAttr.get('nodata',''))>0:
            noData = " --no-data "
        else:
            noData = ""
        if len(inAttr.get('locktables',''))>0:
            skipLocks = ""
        else:
            skipLocks = " --skip-add-locks "
        if len(inAttr.get('extendedinsert',''))>0:
            extInsert = ""
        else:
            extInsert = " --extended-insert "
        if len(inAttr.get('compress',''))>0:
            compressSend = ""
        else:
            compressSend = " --compress "


        tabDir = inAttr.get('tabdir','')
        if len(dumpTables)>0:
            dumpTables = " --tables " + dumpTables
        if len(tabDir)>0:
                        tabDir = ' --tab="' + tabDir + '"'
        destFile = self.props.get('dest_file','')
        if len(destFile)>0:
            dumpFile = " > " + os.path.join(self.props['destPath'],destFile)
            # Can't do both
            tabDir = ''
        else:
            dumpFile = ''
        destDB = self.props.get('dest_db_name','')
        # If this is a pipe transfer, eliminate tab and dump
        if(len(destDB)>0):
            tabDir = ''
            dumpFile = ''
            pathMySQL = 'mysql' #os.path.normpath(os.path.join(self.props['path_mysql'],'mysql'))
            destHost = self.props.get('dest_db_host','')
                        destUsername = self.props.get('dest_db_username','')
                        destPassword = self.props.get('dest_db_password','')
                        destPort =  self.props.get('dest_db_port','')
                        destSocket =  self.props.get('dest_db_socket','')

            if destHost:
                destHost = " -h " + destHost
                        if destUsername:
                                destUsername = " -u " + destUsername
                        if destPassword:
                                destPassword = " -p" + destPassword
                        if destPort:
                                destPort = ' -P'+destPort+' '
                        if destSocket:
                                destSocket = ' --socket='+destSocket+' '
            pipeDir = " | "+pathMySQL+" "+destHost+destUsername+destPassword+destPort+destSocket+" "+destDB

        socketStr = self.props.get('db_socket','')
        if socketStr:
            socketStr = " --socket="+socketStr+' '
        pathMySQLDump = os.path.normpath(os.path.join(self.props['path_mysql'],'mysqldump'))
        cmdStr = pathMySQLDump+" -h "+self.props['db_host']+" -u "+self.props['db_username']+" -p"+self.props['db_password']+" -P"+str(self.props['db_port'])+noData+socketStr+" --databases "+self.props['db_name']+" "+dumpTables+dumpFile+extInsert+skipLocks+compressSend+tabDir+pipeDir
        print "\n"+cmdStr+"\n"
        returnArray = self.doExec(cmdStr)
        print ''.join(returnArray)

    def  taskDBImport(self,inAttr=None):
        importFiles = inAttr.get('path','')
        print "Importing:"+self.props['db_name'] + " " + importFiles
        if True:
                        destHost = self.props.get('dest_db_host','')
                        destUsername = self.props.get('dest_db_username','')
                        destPassword = self.props.get('dest_db_password','')
            destPort =  self.props.get('dest_db_port','')
                        destSocket =  self.props.get('dest_db_socket','')


                        if destHost:
                                destHost = " -h " + destHost
                        if destUsername:
                                destUsername = " -u " + destUsername
                        if destPassword:
                                destPassword = " -p" + destPassword
            if destPort:
                destPort = ' -P'+destPort
                        if destSocket:
                                destSocket = ' --socket='+destSocket



            importFiles = " " +os.path.join(self.props['destPath'],importFiles)
            pathMySQL = os.path.join(self.props['path_mysql'],'mysqlimport')
            cmdStr = os.path.normpath(pathMySQL)+destHost+destUsername+destPassword+destPort+destSocket+" "+self.props['dest_db_name']+" "+importFiles
            #print cmdStr
            returnArray = self.doExec(cmdStr)
            print ''.join(returnArray)

# -----------------------------  End Tasks -----------------------------

    def processFile(self,inDir,inFile):
        if self.testMode:
            pass
            #print "Processing file:"+inDir+inFile
        if self.props['archiveFile']:
            if self.testExtension(inFile):
                zipType = zipfile.ZIP_STORED
            else:
                zipType = zipfile.ZIP_DEFLATED
            #self.curZip = zipfile.ZipFile(archivePath+archiveFile+"_"+str(self.curZipInc)+".zip",'w')
            archiveSize = os.stat(self.curArchiveName).st_size
            oneMeg = 1000000
            oneGig = 1000 * oneMeg
            fileLimit = 600 * oneMeg
            if archiveSize - fileLimit > 1:
                self.curZip.close()
                self.curZipInc += 1
                self.curArchiveName = os.path.join(self.props['destPath'],self.props['archiveFile']+"_"+str(self.curZipInc)+".zip")
                self.curZip = zipfile.ZipFile(self.curArchiveName,'w',zipfile.ZIP_DEFLATED)
                self.archiveList.append(self.curArchiveName)
                print archiveSize,
        if self.testMode:
            print "Zipping file:"+os.path.join(inDir,inFile)
        else:
            try:
                inDir = inDir.encode('ascii','ignore')
                inFile = inFile.encode('ascii','ignore')
                self.curZip.write(os.path.join(inDir,inFile),None,zipType)
            except (IOError, os.error), why:
                print "Can't copy %s to %s: %s" % (os.path.join(inDir,inFile), '', str(why))
        return zlib.crc32(inFile)

    def processDir(self,inDir,recurse=False,inLog=False):
        self.returnStr = ""
        inDir = os.path.abspath(inDir)
        i = 0
        if recurse:
            if self.testMode:
                print "Beginning recurse of:"+inDir
            for curPath,dirs,files in os.walk(inDir):
                for inName in files:
                    result = self.processFile(curPath,inName)
                    i += 1
                    if result:
                        if(inLog):
                            inLog.write(result)
                            inLog.flush()
                        else:
                            self.returnStr += "" #result
                    self.report(os.path.join(curPath,inName),1)
                    #self.report(" Files:"+str(i)+"\n")
                    #if (i % 40)==0:
                    #	print " Files:"+str(i)+"\n"
                        #self.returnStr = ""
                    #if inName[-3:] == "php":
                    #	processFile(inName,curPath,walkLog)
                    #print inName
                    #if inName[-2:] == "as":
                    #	processFile(inName,curPath,walkLog)
                        #g.es(inName+"\t"+curPath+"\t"+str(fSize)+"\t"+str(fLines)+"\t")
                if self.ignoreSVN:
                    if '.svn' in dirs:
                        dirs.remove('.svn')  # don't visit CVS directories
            #walkLog.close()
        return True

    def startCopy(self,inDir,recurse,inLog=False):
        print "Starting copy..."
        #elif(self.cmdOptions.copydir):
        #self.copyFiles(self.cmdOptions.copydir, self.cmdOptions.destination)
        #else:
        if self.cmdOptions.noarchive:
            print "No archiving, just transfer file:"+self.cmdOptions.noarchive
            self.archiveList.append(self.cmdOptions.noarchive)
        else:
            if archiveFile:
                self.curArchiveName = archivePath+archiveFile+"_"+str(self.curZipInc)+".zip"
                self.curZip = zipfile.ZipFile(self.curArchiveName,'w') # ,zipfile.ZIP_DEFLATED
                self.archiveList.append(self.curArchiveName)
            self.processDir(inDir,recurse,inLog)
            if archiveFile:
                self.curZip.close()
        if self.cmdOptions.ftpdest:
            print "\nStarting ftp to "+self.cmdOptions.ftpdest+"..."
            self.ftpArchiveList(self.cmdOptions.ftpdest,"root","mypassword")
        # TODO: Activate the command line Task
        if self.cmdOptions.ftpdest == 'task':
            curType = 'svn'
        print "Copy complete."

    def createTargetList(self,xmlDOM):
        targets2 = xmlDOM.getElementsByTagName("target")
        for target in targets2:
            curType=target.localName
            if curType:
                targetName =  target.getAttribute('name')
                self.targetList[targetName] = target
        self.tags['availabletargets'] = ", ".join(self.targetList.keys())

    def getAttr(self,inNode,attrName,defaultVal=''):
        try:
            if inNode.hasAttribute(attrName):
                return inNode.getAttribute(attrName)
            else:
                return defaultVal
        except:
            return ''
    # Execute each command in the XML batch script
    def executeScript(self,xmlDOM,parentName='project',targetDefault=''):
        #print "Starting executeScript"
        if parentName=='project':
            execStartTime = strftime("%H:%M")
        #targetParent = xmlDOM.getElementsByTagName(parentName).item(0)
        #print xmlDOM.getElementsByTagName(parentName)
        if len(targetDefault)==0:
            targetDefault = self.getAttr(xmlDOM,'default','')

        # Check if there is a target that needs to be executed before this one
        execBeforeStr = self.getAttr(xmlDOM,'depends','')
        execBeforeStr = self.getAttr(xmlDOM,'execbefore',execBeforeStr)
        execBeforeStr = self.replaceTags(execBeforeStr)
        if(len(execBeforeStr)>0):
            execBeforeArray = execBeforeStr.split(',')
            for execBefore in execBeforeArray:
                if(len(execBefore)>0 and execBefore in self.targetList):
                    # If new target has a default, set it for the recursive call
                    defaultInTarget = self.getAttr(self.targetList[execBefore],'default','')
                    # Check the other names that this attribute might be under
                    defaultInTarget = self.getAttr(self.targetList[execBefore],'execafter',defaultInTarget)
                    #print "Executing before:"+execBefore
                    defaultInTarget = self.replaceTags(defaultInTarget)
                    self.executeScript(self.targetList[execBefore],'target',defaultInTarget)
                else:
                    print "Could not find target:"+execBefore


        #targetDefault = xmlDOM.getElementsByTagName(parentName).item(0).getAttribute('default')
        targets = xmlDOM.childNodes
        finished = False
        for target in targets:
            curType=target.localName
            if curType:
                # If item has enabled attribute set to zero, move to the next one
                if target.getAttribute('enabled') != '0' and not finished:
                    # Create a dictionary of the current XML attributes
                    attrList = {}
                    if target.attributes:
                        attrList = {}
                        for attr in target.attributes.keys():
                            attrList[attr]=target.attributes[attr].value
                    # Set common attributes
                    if target.getAttribute('src'):
                        self.props['srcPath'] = self.replaceTags(str(target.getAttribute('src')))
                    if target.getAttribute('dest'):
                        self.props['destPath'] = self.replaceTags(str(target.getAttribute('dest')))

                    if curType == 'copy':
                        if self.testMode:
                            print self.curSpaces+"Copy src:"+target.getAttribute('src')+" dest:"+target.getAttribute('dest')
                        else:
                            self.taskCopy({'src':target.getAttribute('src'),'dest':target.getAttribute('dest')})
                    elif curType == 'ftp':
                        #self.props['srcPath'] = self.replaceTags(str(self.props['srcPath']))
                        if self.testMode:
                            print self.curSpaces+"ftp src:"+target.getAttribute('src')+" dest:"+target.getAttribute('dest')
                        self.taskFTP(self.props['srcPath'],target.getAttribute('dest'),target.getAttribute('username'),target.getAttribute('password'))
                    elif curType == 'zip':
                        self.props['archiveFile'] = self.replaceTags(str(target.getAttribute('archiveFile')))
                        if self.testMode:
                            print self.curSpaces+"zip src:"+target.getAttribute('src')+" dest:"+target.getAttribute('dest')+" archiveFile:"+target.getAttribute('archiveFile')
                        self.taskZip(self.props['srcPath'],self.props['destPath'],self.props['archiveFile'])
                    elif curType == 'pause':
                        if self.testMode:
                            print self.curSpaces+"pause"
                        a = raw_input("Press the ENTER key to continue...")
                        print a
                    elif curType == 'input':
                        if self.testMode:
                            print self.curSpaces+"pause"
                        else:
                            msg = "Do you want to continue(y)?"
                            if target.getAttribute('msg'):
                                msg = target.getAttribute('msg')
                            answer = raw_input(msg)
                            if answer != "y":
                                print "Operation aborted."
                                finished = True
                    elif curType == 'exec':
                        if self.testMode:
                            print self.curSpaces+"exec"
                        self.taskExec(target.attributes)
                    elif curType == 'crontab':
                        if self.testMode:
                            print self.curSpaces+"crontab"
                        self.taskCrontab(attrList)
                    elif curType == 'joomla':
                        if self.testMode:
                            print self.curSpaces+"joomla"
                        self.taskJoomla(attrList)
                    elif curType == 'mysql' or curType == 'dbsummary' :
                        self.props['action'] = str(target.getAttribute('action'))
                        if target.getAttribute('db_name'):
                            self.props['db_name'] = str(target.getAttribute('db_name'))
                        if target.getAttribute('db_host'):
                            self.props['db_host'] = str(target.getAttribute('db_host'))
                        if target.getAttribute('db_username'):
                            self.props['db_username'] = str(target.getAttribute('db_username'))
                        if target.getAttribute('db_password'):
                            self.props['db_password'] = str(target.getAttribute('db_password'))
                        if target.getAttribute('db_port'):
                            self.props['db_port'] = str(target.getAttribute('db_port'))
                        if target.getAttribute('db_socket'):
                            self.props['db_socket'] = str(target.getAttribute('db_socket'))

                        if target.getAttribute('sp_user'):
                            self.props['sp_user'] = str(target.getAttribute('sp_user'))
                        if target.getAttribute('dest_file'):
                            self.props['dest_file'] = self.replaceTags(str(target.getAttribute('dest_file')))
                        self.props['query'] = str(target.getAttribute('query'))
                        self.props['msg'] = str(target.getAttribute('msg'))
                        if self.testMode:
                            print self.curSpaces+curType
                        else:
                            if curType == 'mysql':
                                self.taskMySQL(attrList)
                            else:
                                self.taskDBSummary(attrList)

                    elif curType == 'log':
                        if self.testMode:
                            print self.curSpaces+"log"
                        else:
                            self.taskLog(attrList)
                    elif curType == 'email':
                        if self.testMode:
                            print self.curSpaces+"email"
                        else:
                            self.taskEmail(attrList)
                    elif curType == 'svn':
                        if self.testMode:
                            print self.curSpaces+"svn"
                        else:
                            self.taskSVN(attrList)
                    elif curType == 'workingdir':
                        if self.testMode:
                            print self.curSpaces+curType
                        else:
                            self.taskWorkingDir(attrList)
                    elif curType == 'mkdir':
                        if self.testMode:
                            print self.curSpaces+curType
                        else:
                            self.taskMkDir(attrList)
                    elif curType == 'property':
                        if target.getAttribute('name'):
                            #print self.curSpaces+"set property '" + target.getAttribute('name') + "' to " + target.getAttribute('value')
                            self.props[target.getAttribute('name')] = self.replaceTags(target.getAttribute('value'))
                    elif curType == 'tag':
                        if target.getAttribute('name'):
                            tempTagVal = ''
                            if target.getAttribute('type') == 'input':
                                tempTagVal = raw_input("Enter a value for the tag "+target.getAttribute('name')+"(default:"+target.getAttribute('value')+"):")
                            if len(tempTagVal)==0:
                                tempTagVal = target.getAttribute('value')
                            tempTagVal =  self.replaceTags(tempTagVal)
                            print self.curSpaces+"set tag '" + target.getAttribute('name') + "' to " + tempTagVal
                            self.tags[target.getAttribute('name')] = tempTagVal
        if(len(targetDefault)>0):
            if(targetDefault in self.targetList):
                # If target uses tags, replace them
                targetDefault = self.replaceTags(targetDefault)
                # If new target has a default, set it for the recursive call
                defaultInTarget = self.getAttr(self.targetList[targetDefault],'default','')
                # Check the other names that this attribute might be under
                defaultInTarget = self.getAttr(self.targetList[targetDefault],'execafter',defaultInTarget)
                defaultInTarget = self.replaceTags(defaultInTarget)
                #print "Executing after:"+targetDefault
                self.executeScript(self.targetList[targetDefault],'target',defaultInTarget)
            else:
                print "Could not find target:"+targetDefault

        if not self.props['quietmode']:
            if parentName=='project':
                print "Script execute complete. ST:"+execStartTime+" ET:"+strftime("%H:%M")

    # Parse the XML batch file
    def loadScript(self,fName):
        f = open(fName,'r')
        xmlStr = f.read()
        f.close()
        return xml.dom.minidom.parseString(xmlStr)

    # Process the command line arguments
    def processArgs(self,options,args):
        if self.cmdOptions.recursive:
            self.props['recursive'] = 1

        if options.quietmode:
            self.props['quietmode']=1
        if self.props['ignoresvndir']:
            if not self.props['quietmode']:
                self.report("Ignoring SVN folders.")
        if options.testmode:
            self.testMode = True
            if not self.props['quietmode']:
                print "*** Test Mode is on ***"

    # Setup install as a Linux alias
    def install():
        pass

    # Register a command for access from the command line
    def registerCommand(self,cmdName, cmdArgs):
        # Set the method that will be called when command is requested
        #cmdArgs['cmdMethod'] = cmdMethod
        self.commandList[cmdName] = cmdArgs

    def registerCoreCommands(self):
        self.addExample('',"python todocopy.py","Execute Todo Copy")
        self.addExample('',"python todocopy.py example_exec.xml","Execute Todo Copy XML script/macro")
        self.addExample('',"python todocopy.py example_exec.xml target1","Execute target1 in XML script")
        self.registerCommand('copy',[self.taskCopy,['src',''],['dest','']])
        self.addExample('copy',	"todocopy.py copy ./ ../yhw_production","Copy files from -> to")
        self.registerCommand('copylist',[self.taskCopyList,['filelist',''],['dest','']])
        self.addExample('copylist',"todocopy.py copylist filelist.txt ../yhw_production","Copy all files in list with automatic path creation")
        self.registerCommand('createlist',[self.taskCreateList,['src',''],['dest',''],['type','newline']])
        self.addExample('createlist',"todocopy.py createlist -r .","Display a list of all files (recursive) in the current dir")
        self.addExample('createlist',"todocopy.py createlist -r . filelist.txt","Output a list of all files (recursive) in the current dir")
        self.registerCommand('ftplist',[self.taskFTPList,['filelist',''],['dest','']])
        self.addExample('ftp',"todocopy.py -l filelist.txt --ftp 205.107.10.199","FTP ")
        self.registerCommand('workingdir',[self.taskWorkingDir,['value','./']])
        self.registerCommand('dbsummary',[self.taskDBSummary,['tablelist','']])
        self.addExample('dbsummary',"todocopy.py dbsummary  -o dbsumm.xml","Generate database summary and output to .xml file")
        self.addExample('dbsummary',"todocopy.py dbsummary tbvenue,tbtasktype -o db.xml","Generate database summary of 2 tables and output to .xml file")
        self.registerCommand('svn',[self.taskSVN,['action',''],['dest','']])
        self.registerCommand('svndir',[self.taskSVNDirList,['action',''],['dest','']])
        self.registerCommand('examples',[self.taskExamples,['type','']])
        self.registerCommand('setpath',[self.taskSetPath,['path','']])
        self.addExample('setpath',"todocopy.py setpath","Adds the cwd to current path -- useful for executing TC from any folder")
        self.registerCommand('md5',[self.taskMD5,['source','']])
        self.addExample('md5',"todocopy.py md5 myplaintext","Returns an MD5 value of the passed plaintext")
        self.registerCommand('sha1',[self.taskSHA1,['source','']])
        self.addExample('sha1',"todocopy.py sha1 myplaintext","Returns an SHA1 value of the passed plaintext")
        self.registerCommand('joomla',[self.taskJoomla,['action',''],['src','']])
        self.registerCommand('findabove',[self.taskFindAbove,['src',''],['filename','']])

        # TODO: Replace these placeholders with real commands
        self.registerCommand('scp',[self.taskSCP,['action',''],['dest','']])
        self.registerCommand('email',[self.taskFTPList,['filelist',''],['dest','']])
        self.registerCommand('log',[self.taskFTPList,['filelist',''],['dest','']])

    def controller(self,options,args):
        usage = "  USAGE --> python todocopy.py command|xmlfile [options] arg1 arg2\n"
        usage += "    For options list, type: python todocopy.py --help"
        self.registerCoreCommands()
        self.props['quietmode']=False
        self.ignoreSVN = True
        self.cmdOptions = options
        self.cmdArgs = args
        # Reset database connection
        self.mysqlconn = None
        autorunList = ["tc_autorun.xml","Makefile"]
        self.processArgs(options,args)
        if not self.props['quietmode']:
            print "--- Todocopy by Dan Rahmel, revision #"+self.getRev()+" --- "
            if len(args)==0:
                print "------> For examples, execute: python todocopy.py examples\n"
        # Check to make sure some switches or arguments were passed into the app -- there is always 1, the path of the script
        if len(sys.argv)<2:
            for autorunFName in autorunList:
                # Try to execute an autorun script
                if os.path.isfile(autorunFName):
                    print "Executing autorun..."
                    tempDOM = self.loadScript(autorunFName)
                    self.createTargetList(tempDOM)
                    self.executeScript(tempDOM)
                    return

        # Check for a TC script file
        elif args[0][-3:].lower()=="xml":
            # Load the XML into a DOM
            tempDOM = self.loadScript(args[0])
            # Harvest references to all targets in DOM
            self.createTargetList(tempDOM)
            # Get the primary project DOM
            projectDOM = tempDOM.getElementsByTagName('project').item(0)
            # If a target is specified, pass that to the execution instead of running the default
            targetDefault = ''
            if len(args)>1:
                targetDefault = args[1]
            self.executeScript(projectDOM,'project',targetDefault)
            return

        elif args[0] in self.commandList:
            argList = {}
            for i in range(1,len(self.commandList[args[0]])):
                tempVal = self.commandList[args[0]][i][1]
                # ignore the command itself
                try:
                    tempVal = args[i]
                except:
                    pass
                argList[self.commandList[args[0]][i][0]] = tempVal
            self.commandList[args[0]][0](argList)
            return
        else:
            srcDir = "c:/TestCompress/"
            archivePath = "c:/"
            archiveFile = "Test_BU022108"
            if len(args)==1:
                if args[0][-3:].lower()=="xml":
                    tempDOM = self.loadScript(args[0])
                    self.createTargetList(tempDOM)
                    projectDOM = tempDOM.getElementsByTagName('project').item(0)
                    print projectDOM
                    self.executeScript(projectDOM)
                    return
            elif len(args)>1:
                # Must be an implicit copy
                argList = {}
                # Start at 1 to ignore the method itself
                for i in range(1,len(self.commandList['copy'])):
                    tempVal = self.commandList['copy'][i][1]
                    try:
                        tempVal = args[i-1]
                    except:
                        pass
                    argList[self.commandList['copy'][i][0]] = tempVal
                self.commandList['copy'][0](argList)
                return
                #self.props['srcPath'] = args[0]
                #archivePath = args[1]
                #self.props['destPath'] = args[1]
                #archiveFile = args[2]
                #self.props['archiveFile'] = args[2]
        print usage


if __name__ == '__main__':
    insTodoCopy = todocopy()
    usage = "  python %prog command|xmlfile [options] arg1 arg2\n"
    parser = OptionParser(usage=usage)
    parser.add_option("-o", "--outfile", dest="outfile",help="output data to OUTFILE", metavar="OUTFILE")
    parser.add_option("-f", "--ftp", dest="ftpdest",help="ftp archive files to FTPDEST", metavar="FTPDEST")
    parser.add_option("-n", "--noarchive", dest="noarchive",help="no file archiving", metavar="ARCHIVENONE")
    parser.add_option("-l", "--list", dest="copylist",help="INI format file of files/dirs to copy", metavar="FILE")
    parser.add_option("-d", "--destination", dest="destination", help="Destination path for operation", metavar="DEST")
    parser.add_option("-s", "--source", dest="source", help="Source path for operation", metavar="SRC")
    parser.add_option("-c", "--copydir", dest="copydir", help="Source directory of files to copy", metavar="COPYDIR")
    parser.add_option("-r", "--recursive",action="store_true", dest="recursive", default=False,help="Perform recursive operation")
    parser.add_option("-e", "--test",action="store_true", dest="testmode", default=False,help="Don't actually copy or create files")
    parser.add_option("-q", "--quiet",action="store_true", dest="quietmode", default=False,help="Turn off copyright messages")
    parser.add_option("-t", "--task", dest="tasktype", help="Task to execute (equivalent to XML tag)", metavar="TASKTYPE")
    parser.add_option("-u", "--username", dest="username", help="Set username", metavar="USERNAME")
    parser.add_option("-[", "--password", dest="password", help="Set password", metavar="PASSWORD")
    (options, args) = parser.parse_args()
    insTodoCopy.controller(options,args)

