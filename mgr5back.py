#!/usr/bin/python 

import sys
import os
import xmltodict
import time

# ID vmmanager of  your node
NodeID='2'
#exclude a virtual machines with should not be backup. 
# example NoBackupID='51,12' - ids are separeted by commas.
NoBackupID='51'
# 
ftp_conn='/usr/local/mgr5/etc/.vmmgr-backup/storages/st_1'
# Pidfile
pidfile = '/tmp/mgr5back.pid'
BackDir='/backup'
#FileDB="/usr/local/mgr5/etc/vmmgr.conf.d/db.conf"
FileDB='/home/ruslan/db.conf'
# You can use script with gzip and without zipping, 
Gzip="YES"   # YES or NO 
SaveDate=9



pid = str(os.getpid())
def Check():
    if os.path.isfile(pidfile):
        print "%s already exists, exiting" % pidfile
        sys.exit()
    else:
        file(pidfile, 'w').write(pid)
        

def Mysqlget(SQL):
    VarMysql={}
    St=['DBHost','DBUser','DBPassword','DBName']
    for line in open(FileDB,'r').readlines():
        parts = line.split() # split line into parts
        if len(parts) > 1: 
            VarMysql[parts[0]] = parts[1]
    import mysql.connector
    from mysql.connector import errorcode
    try:
        cnx = mysql.connector.connect(user=VarMysql['DBUser'], password=VarMysql['DBPassword'],
                                host=VarMysql['DBHost'],
                                database=VarMysql['DBName'])
    except mysql.connector.Error as err:
        if err.errno == errorcode.ER_ACCESS_DENIED_ERROR:
            print("Something is wrong with your user name or password")
        elif err.errno == errorcode.ER_BAD_DB_ERROR:
            print("Database does not exist")
        else:
            print(err)
    else:
        cur = cnx.cursor()
        cur.execute(SQL)
        Servs=list(cur.fetchall())
        cnx.close()
    return Servs

def Search():
   sql="select id from vm where hostnode=\'%s\' and id not in (%s);"%(NodeID, NoBackupID)
   Servs=Mysqlget(sql)
   for R in Servs:
       StartBackup(R[0])

def StartBackup(ServerID):
    import datetime
    date=datetime.datetime.now().strftime("%Y%m%d%H%M%S")
    #print ServerID
    sql="select vm,name,pool,size from volume where vm=\'%s\' and hostnode=\'%s\' and pool is not NULL;"%(ServerID,NodeID)
    Serv=Mysqlget(sql)
    #print Serv
    for R in Serv:
        #print R[0]
        W=work(R[0], R[1], R[2], date)
        W.CreateLVM(R[3])
    for R in Serv:
        W=work(R[0], R[1], R[2], date)
        if Gzip is "YES":
            W.CreateGzip()
        W.PutFtp()
        W.RemoveLVM()
        if Gzip is "YES":
            W.RmFile()
        Clean(R[0])

class work:
    def __init__(self, id,  Name, Pool, date):
        self.id=str(id)
        self.date=date
        self.Name=Name
        self.Pool=Pool
        self.PoolName='/dev/'+Pool+"/"+Name
        self.filez=BackDir+"/"+Name+"_"+date
        self.NameImgFtp=Name+"_"+date
        self.dftp=self.Name+"/"+date
        if Gzip is "YES":
            self.filez=BackDir+"/"+Name+"_"+date
        else:
            self.filez=self.PoolName
        #print PoolName
    def CreateLVM(self, Size):
     #   print "Name: ", self.Name," Size:  ", Size," Pool: "+ self.Pool
        print "Start creating LVM Snapshote "+self.Name
        cmd0="virsh send-key %s KEY_LEFTALT KEY_SYSRQ KEY_S"%(Name)
        cmd1="lvcreate -L%sM -s -n %s-snapshot %s"%(Size,self.Name,self.PoolName)
        os.system(cmd0)
        import time
        time.sleep(5)
        os.system(cmd1)
    def RemoveLVM(self):
        print "Remove LVM Snapshote "+self.PoolName
        cmd="lvremove -f %s-snapshot"%(self.PoolName)
        os.system(cmd)
    def RmFile(self):
        print "Remove file:"+self.filez
        cmd="rm %s"%(self.filez)
        os.system(cmd)
    def CreateGzip(self):
        print "Create gzip file, pool: "+self.Pool+" backup file: "+self.filez
        cmdDD="dd if=%s-snapshot | gzip -c > %s "%(self.PoolName, self.filez)
        os.system(cmdDD)  # start dd
    def PutFtp(self):
        #print self.Name
        DIR=NodeID+"/"+self.id+"/"+self.date
        w=workftp()
        w.Path(NodeID)
        w.Path(self.id)
        w.Path(self.date)
        print "Upload to "+DIR
        w.Put(self.NameImgFtp, self.filez)

    
class workftp():
    def __init__(self):
        import ftplib
        from ftplib import FTP
        print "Connect to FTP server"
        with open(ftp_conn) as fd:
            doc = xmltodict.parse(fd.read())
            nameb=doc['doc']['name']
            self.passftp=doc['doc']['settings']['password']
            self.url=doc['doc']['settings']['url']
            self.user=doc['doc']['settings']['username']
        self.ftp = FTP(self.url)
        self.ftp.login(self.user, self.passftp)
    def Path(self, path):
        import ftplib
        from ftplib import FTP
        try:
            self.ftp.cwd(path)
        except ftplib.error_perm:
            self.ftp.mkd(path)
            self.ftp.cwd(path)
    def Put(self,  NameFile, File):
        self.ftp.storbinary("STOR %s"%(NameFile), open(File))
        self.ftp.quit()
    def List(self): 
        files = self.ftp.nlst()
        return files

    
def Clean(id):
    print "Start clean ftp server, older then:", SaveDate,"days"
    w=workftp()
    path=NodeID+"/%s/"%(id)
    w.ftp.cwd(path)
    ListDirs=w.List() 
    import datetime
    date=datetime.datetime.now() - datetime.timedelta(days=SaveDate)
    date2 = date.strftime("%Y%m%d000000")
    print "Check date: "+date2
    for R in ListDirs:
        if date2 > R:
            w.ftp.cwd(R)
            ListFile=w.List()
            for F in ListFile:
                print "Delete file:"+F
                w.ftp.delete(F)
            print "Detele Dir: "+R
            w.ftp.cwd("~/"+path)
            w.ftp.rmd(R)    # Delete old dir
    w.ftp.quit()

    
def Main(): 
    if len(sys.argv) > 1:
         StartBackup(sys.argv[1])
    else:
        Check()
        Search()
        os.remove(pidfile)
       #Clean("151") 
    #sql="select name,pool,size from volume where hostnode=\'%s\' and vm not in (%s) and pool is not NULL;"%(NodeID, NoBackupID)
    #res=Mysqlget(sql)
    #print res
    
    
if __name__ == '__main__':
    Main()

