# -*- coding: utf-8 -*-
"""
    This program is free software; you can redistribute it and/or modify
    it under the terms of the GNU General Public License as published by
    the Free Software Foundation; either version 3 of the License,
    or (at your option) any later version.

    This program is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.
    See the GNU General Public License for more details.

    You should have received a copy of the GNU General Public License
    along with this program; if not, see <http://www.gnu.org/licenses/>.

    based on original worf of: draugr

    @author: t4skforce
"""

import ConfigParser, re, os, urllib
from os.path import exists
from module.lib.BeautifulSoup import BeautifulSoup, SoupStrainer
from module.plugins.Hook import Hook
from module.utils import save_join, save_path, html_unescape
from shutil import move
from time import sleep
import hashlib

baseUrl = "http://www.icefilms.info"

def extractSeasonAndEpisodeNum(episodeString):
    # S01E04 / s1E04 / S1e4
    m = re.search( r'(\A|\D)s([0-9]{1,2})e([0-9]{1,2})(\D|\Z)', episodeString, re.I )
    if not m:
        # 7x04 / 07x4 / 7x4 / 07x04
        m = re.search( r'(\A|\D)([0-9]{1,2})x([0-9]{1,3})(\D|\Z)', episodeString, re.I )

    if m:
        # number of season, number of episode
        return int(m.group(2)), int(m.group(3))
    else:
        return -1, -1
    

class Show():
    def __init__(self, hook, showName, showDir, showUrl, hd, exclSeasons, exclEpisodes, format, queue):
        self.hook = hook
        self.showName = showName
        self.showDir = showDir
        self.showUrl = showUrl
        self.hd = hd
        self.exclSeasons = exclSeasons
        self.exclEpisodes = exclEpisodes
        self.format = format
        self.queue = queue
        
        self.httpReq = self.hook.core.requestFactory.getRequest(hook.__name__)
        self.episodesOnDisk = {}
        self.episodesToDownload = []
    
    def syncronize(self):
        # read existing episodes
        self.episodesOnDisk = {}
        self.loadEpisodesOnDisk(self.showDir)
        
        # process every episode link and check if it needs to be downloaded
        showHtml = self.loadHtml(self.showUrl)
        if showHtml == '':
            return False
        linkStrainer = SoupStrainer('a')
        showLinkSoup = BeautifulSoup(showHtml, parseOnlyThese=linkStrainer)
        
        for a in showLinkSoup.findAll('a', attrs={'href': re.compile('/ip\.php\?v=.*')}):
            if not a.string:
                continue
            
            ep = Episode(self, a['href'], a.string)
            
            if ep.seasonNum == -1:
                self.hook.logError('Unable to extract episode info from %s' % a.string)
                continue
            if self.excluded(ep.seasonNum, ep.episodeNum):
                self.hook.logDebug('skipping, excluded => %s - S%02dE%02d - %s' % (self.showName, ep.seasonNum,ep.episodeNum,ep.episodeName))
                continue
            if self.onDiskAlready(ep.seasonNum, ep.episodeNum):
                self.hook.logDebug('skipping, already downloaded => %s - S%02dE%02d - %s' % (self.showName, ep.seasonNum,ep.episodeNum,ep.episodeName))
                continue
                        
            if ep.refreshDownloadLink():
                self.hook.logDebug('downloading => %s - S%02dE%02d - %s' % (self.showName, ep.seasonNum,ep.episodeNum,ep.episodeName))
                self.episodesToDownload.append({'season': ep.seasonNum, 'episode': ep.episodeNum, \
                        'name': ep.episodeName, 'url': ep.url['download'], 'showDir': self.showDir})
                #ep.printInfo()
        
        # prevent duplicate downloads, add downloads and store target filepath of file url
        self.removeAlreadyQueuedEpisodes()
        self.addDownloads()
        self.storeNameInfo(self.episodesToDownload)

    # store filepath for every url
    # Needed for renaming file after it is downloaded
    def storeNameInfo(self, episodesInfo):
        for ep in episodesInfo:
            if self.format == "{show name}/Season 01/S01E01 - {episode name}":
                filepath = save_join(ep['showDir'], "Season %02d" % ep['season'], \
                                "S%(season)02dE%(episode)02d - %(name)s" % \
                                {'season': ep['season'], 'episode': ep['episode'], 'name': ep['name'] })
            elif self.format == "{show name}/Season 01/1x01 - {episode name}":
                filepath = save_join(ep['showDir'], "Season %02d" % ep['season'], \
                                "%(season)02dx%(episode)02d - %(name)s" % \
                                {'season': ep['season'], 'episode': ep['episode'], 'name': ep['name'] })
            elif self.format == "{show name}/S01E01 - {episode name}":
                filepath = save_join(ep['showDir'], "S%(season)02dE%(episode)02d - %(name)s" % \
                                {'season': ep['season'], 'episode': ep['episode'], 'name': ep['name'] })
            else:
                filepath = save_join(ep['showDir'], "%(season)02dx%(episode)02d - %(name)s" % \
                                {'season': ep['season'], 'episode': ep['episode'], 'name': ep['name'] })
            # save url for lookup later
            self.hook.setStorage(ep['url'], filepath)

    def loadEpisodesOnDisk(self, showDir):
        # store season and episode number of already available episodes
        try:
            for entry in os.listdir(showDir):
                if os.path.isfile(save_join(showDir,entry)):
                    seasonNum, episodeNum = extractSeasonAndEpisodeNum(entry)
                    if seasonNum > -1 and episodeNum > -1:
                        self.episodesOnDisk[(seasonNum,episodeNum)] = 1
                else:
                    self.loadEpisodesOnDisk(save_join(showDir,entry))
        except Exception,e:
            pass
    
    def onDiskAlready(self, seasonNum, episodeNum):
        if self.episodesOnDisk.has_key((seasonNum,episodeNum)):
            return True
        else:
            return False

    def excluded(self, seasonNum, episodeNum):
        if str(seasonNum) in self.exclSeasons:
            return True
        for exclEpisode in self.exclEpisodes:
            exclSNum, exclENum = extractSeasonAndEpisodeNum(exclEpisode)
            if seasonNum == exclSNum and episodeNum == exclENum:
                return True
        return False
    
    def removeAlreadyQueuedEpisodes(self):
        if len(self.episodesToDownload) < 1:
            return

        # prevent downloading the same file multiple times
        allQueuedUrls = {}
        allCollectorFiles = self.hook.core.db.getAllLinks(0)
        allQueueFiles = self.hook.core.db.getAllLinks(1)
        
        for value in allCollectorFiles.itervalues():
            allQueuedUrls[value["url"]] = 1
        for value in allQueueFiles.itervalues():
            allQueuedUrls[value["url"]] = 1
        
        episodesToDownloadTmp = []
        for ep in self.episodesToDownload:
            if not allQueuedUrls.has_key(ep['url']):
                episodesToDownloadTmp.append(ep)
        
        self.episodesToDownload = episodesToDownloadTmp
    
    def addDownloads(self):
        downloadUrls = self.getDownloadUrls()
        if len(downloadUrls) < 1:
            return
        
        packageName = os.path.split(self.showDir)[1]
        self.hook.core.api.addPackage(packageName.encode("utf-8"), downloadUrls, 1 if self.queue else 0)

    def getDownloadUrls(self):
        urls = []
        for ep in self.episodesToDownload:
            urls.append(ep['url'])
        return urls
    
    def loadHtml(self, url, postData={}):
        trycount = 0
        html = ''
        
        while trycount < 3:
            try:
                trycount += 1
                html = self.httpReq.load(url, post=postData)
                break
            except:
                if trycount == 3:
                    self.hook.logError('Failed to download website content (%s)' % url)
                else:
                    sleep(0.2)
        return html
    
    def __str__(self):
        return "{ showDir:%s, showUrl:%s, hd:%s, exclSeasons:%s, exclEpisodes:%s, format:%s, queue:%s }" %(self.showDir,self.showUrl,self.hd,self.exclSeasons,self.exclEpisodes,self.format,self.queue)
            

class Episode():
    seasonNum = -1
    episodeNum = -1
    episodeName = ''
    url = {}
    
    def __init__(self, show, epPageLink, linkText):
        self.url['epPage'] = epPageLink
        self.seasonNum, self.episodeNum = extractSeasonAndEpisodeNum(linkText)
        m = re.search(r'\S*\s(.*)', linkText)
        if m:
            self.episodeName = html_unescape(m.group(1))
        self.show = show

    def refreshDownloadLink(self):
        self.url['download'] = ''
        # get iframe url
        epPageHtml = self.show.loadHtml(baseUrl+self.url['epPage'])
        if epPageHtml == '':
            return False
        epPageStrainer = SoupStrainer('iframe')
        epPageSoup = BeautifulSoup(epPageHtml, parseOnlyThese=epPageStrainer)
        iframeUrl = epPageSoup.find('iframe', {'id': 'videoframe'} )['src']
        
        del epPageHtml
        del epPageStrainer
        del epPageSoup
        
        # get iframe
        iframeHtml = self.show.loadHtml(baseUrl+iframeUrl)
        if iframeHtml == '':
            return False
        iframeSoup = BeautifulSoup(iframeHtml)

        # downloadIds (separated in hd and everything else)   
        idsHD = {}
        idsOther = {}
        for div in iframeSoup.findAll('div', {'class': 'ripdiv'}):
            if div.b and div.b.string.count("HD") > 0:
                hdDiv = True
            else:
                hdDiv = False

            for a in div.findAll('a', attrs={'onclick': re.compile('go\(\d+\)')}):
                hn = a.find('span')
                if not hn:
                    img = a.find('img')
                    if not img:
                        self.show.hook.logWarning('Name of file hoster not found')
                        self.show.hook.logDebug(a)
                        continue
                    else:
                        hoster = img["alt"].strip().lower()
                else:
                    hoster = hn.getText().strip().lower()
                
                # if more than one file per hoster is available, 
                # some idÂ´s get overridden, but thats ok. We only need one dlink...
                if hdDiv:
                    idsHD[hoster] = a['onclick'][3:-1]
                else:
                    idsOther[hoster] = a['onclick'][3:-1]

        # choose file to download
        downloadId = 0
        if self.show.hd and len(idsHD) > 0:
            for hoster in self.show.hook.preferredHosters:
                if idsHD.has_key(hoster):
                    downloadId = idsHD[hoster]
                    break
                else:
                    downloadId = idsHD.values()[-1] #memorize latest id
        elif len(idsOther) > 0:
            for hoster in self.show.hook.preferredHosters:
                if idsOther.has_key(hoster):
                    downloadId = idsOther[hoster]
                    break
                else:
                    downloadId = idsOther.values()[-1] #memorize latest id
        if downloadId == 0:
            self.show.hook.logError('No download id found for %s' % self.getEpCodeStr())
            return False
        
        # secret value and videoId
        secret = ''
        videoId = ''
        for line in iframeHtml.split('\n'):
            if line.find("f.lastChild.value=") >= 0:
                m = re.search('(?<=f.lastChild.value=")\w+', line)
                secret = m.group(0)
                m = re.search('(?<="&t=)\d+', line)
                videoId = m.group(0)
                break
        if secret == '':
            self.show.hook.logError('Secret not found for %s' % self.getEpCodeStr())
            return False
        if videoId == '':
            self.show.hook.logError('Video id not found for %s' % self.getEpCodeStr())
            return False
        
        # assemble download post data string
        postData = 'id='+downloadId+'&s=4&iqs=&url=&m=-141&cap=&sec='+secret+'&t='+videoId
        
        # get download url
        ajaxUrl = 'http://www.icefilms.info/membersonly/components/com_iceplayer/video.phpAjaxResp.php'
        downloadUrlHtml = self.show.loadHtml(ajaxUrl, postData)
        if downloadUrlHtml == '':
            return False
        if len(downloadUrlHtml) > 2:
            self.url['download'] = urllib.unquote(downloadUrlHtml.split('?url=')[1])
        else:
            self.show.hook.logError('Unable to retrieve download link (%s: %s)' % self.getEpCodeStr(), downloadUrlHtml )
            return False
        
        return True
    
    def getEpCodeStr(self):
        return 'S%(season)02dE%(episode)02d' % {'season':self.seasonNum,'episode':self.episodeNum}

    def printInfo(self):
        print self.getEpCodeStr() + ': ' + self.episodeName
        print self.url['download']


class IcefilmsShowSyncer(Hook):
    __name__ = "IcefilmsShowSyncer"
    __version__ = "0.6"
    __description__ = """syncronizes your TV shows with these available on icefilms.info"""
    __config__ = [("activated", "bool", "Activated", False),
                  ("interval", "int", "Check interval in hours", "12"),
                  ("queue", "bool", "Move new episodes directly to queue", True),
                  ("renameAndMoveFile", "bool", "Rename and move downloaded file to series dir", True),
                  ("format", "{show name}/Season 01/S01E01 - {episode name};{show name}/Season 01/1x01 - {episode name};{show name}/S01E01 - {episode name};{show name}/1x01 - {episode name}", "Naming scheme<br>(used by 'rename and move')", ""),
                  ("showsBaseDir", "folder", "Directory containing all series subdirectories", "./"),
                  ("showsCfgFile", "file", "Config file specifying all shows to sync", "./icefilmsShowSyncer.conf"),
                  ("preferredHosters", "str", "comma-separated list of preferred file hosters", "")]
    __author_name__ = ("t4skforce")
    __running__ = False
    __threaded__ = ["downloadFinished"]
    
    def setup(self):
        self.interval = self.getConfig("interval") * 3600
        
    def configIsValid(self):
        """Checks hook config and returns True if config is valid otherwise False. Writes info to log."""
        valid = True
        
        showsBaseDir = self.getConfig("showsBaseDir")
        if not exists(showsBaseDir):
            self.logError('Shows base directory "%s" doesn\'t exist.' % showsBaseDir)
            valid = False
        
        showsCfgFile = self.getConfig("showsCfgFile")
        if not exists(showsCfgFile):
            self.logError('Series configuration file not found.')
            valid = False
        return valid
    
    def seriesCfgIsValid(self, seriesCfg, series):
        """Checks series config (file) and returns True if config is valid otherwise False. Writes info to log."""
        valid = True
        
        try:
            #check if url has valid format
            paramName = 'url'
            url = seriesCfg.get(series, 'url')
            if not re.match("http://www\.icefilms\.info/tv/series/\d/\d+$", url):
                self.logError('Invalid URL in series %s' % series)
                self.logError(' url has to be like http://www.icefilms.info/tv/series/d/ddd')
                valid = False
            #check quality setting
            try:
                paramName = 'hdPreferred'
                seriesCfg.getboolean(series, 'hdPreferred')
            except ValueError:
                self.logError('invalid value for hdPreferred in series configuration %s. Allowed: 1 or 0' % series )
                valid = False
            #check episodes to ignore
            paramName = 'excludedEpisodes'
            if not re.match( r'((s[0-9]{2}e[0-9]{2})|([0-9]{1,2}x[0-9]{1,2})[\s;,]?)*', seriesCfg.get(series, 'excludedEpisodes'), re.I ):
                self.logError('Format of episodes to ignore invalid')
                valid = False
            #check seasons to ignore
            paramName = 'excludedSeasons'
            if not re.match( r'(\d+[\s;,]?)*', seriesCfg.get(series, 'excludedSeasons'), re.I ):
                self.logError('Format of seasons to ignore invalid')
                valid = False
                
            # allow queue config per series, default with global config
            try:
                seriesCfg.get(series, 'queue')
            except ConfigParser.NoOptionError:
                seriesCfg.set(series, 'queue',str(self.getConfig("queue")))    
                
        except Exception,e:
            self.logError(type(e))
            self.logError('Invalid value or parameter not found: [%(seriesName)s] -> %(param)s' % {'seriesName': series, 'param': paramName })
            valid = False
        return valid

    def printSeriesCfgInfo(self, config):
        numShows = 0
        showsActivated = 0
        for showName in config.sections():
            numShows += 1
            if config.getboolean(showName, 'active'):
                showsActivated += 1
        self.logInfo('Shows active: %(active)s / %(total)s' % {'active': showsActivated, 'total': numShows})

    def periodical(self):
        if not self.configIsValid():
            self.setConfig("activated", False)
            self.logWarning('deactivated because of invalid config.')
            return

        # sleep 10 secs in case pc just woke up and 
        #  network connection is not yet established
        sleep(10)

        # prepare names of preferred hosters
        self.preferredHosters = self.getConfig("preferredHosters").strip().split(',')
        if len(self.preferredHosters[0]) == 0:
            self.preferredHosters = {}
        if len(self.preferredHosters) > 0:
            for i in range(len(self.preferredHosters)):
                self.preferredHosters[i] = self.preferredHosters[i].strip()

        seriesCfg = ConfigParser.RawConfigParser()
        parsedCfgFiles = seriesCfg.read(self.getConfig("showsCfgFile"))
        self.logInfo( 'Processed config file(s): %s' % str.join(',', parsedCfgFiles) )

        self.printSeriesCfgInfo(seriesCfg)
        
        for showName in seriesCfg.sections():
            if not seriesCfg.getboolean(showName, 'active'):
                continue
            if not self.seriesCfgIsValid(seriesCfg, showName):
                continue

            self.logInfo('Syncronizing %s' % showName)
            
            showUrl = seriesCfg.get(showName, 'url')
            showHdPreferred = seriesCfg.getboolean(showName, 'hdPreferred')
            showExclEpisodes = re.findall(r'\w+', seriesCfg.get(showName, 'excludedEpisodes').lower())
            showExclSeasons = re.findall(r'\w+', seriesCfg.get(showName, 'excludedSeasons'))
            showDirFmt = self.getConf('format')
            showsBaseDir = self.getConfig("showsBaseDir")
            showDir = save_join(self.core.api.getConfigValue('general','download_folder'), showsBaseDir , save_path(showName))
            queue = seriesCfg.getboolean(showName, 'queue')
            self.logDebug("%s queue=%s"%(showName,queue))
            show = Show(self, showName, showDir, showUrl, showHdPreferred, showExclSeasons, showExclEpisodes, showDirFmt, queue)
            self.logDebug(show)
            show.syncronize()
            
        self.logInfo('Finished')

    def downloadFinished(self, pyfile):
        if not self.getConf('renameAndMoveFile'):
            return
        
        # try to get the target filename (and path) (without extension) from storage.
        # If finished file was added by this hook, then there is a target filename
        targetfile = self.getStorage(pyfile.url)
        if targetfile:
            self.delStorage(pyfile.url)
            
            # append filename extension
            ext = os.path.splitext(pyfile.name)[1]
            targetfile = targetfile+ext
            
            # get full path of source file
            downloadDir = self.core.api.getConfigValue('general','download_folder')
            packageDir = self.core.api.getPackageInfo(pyfile.packageid).folder
            sourcefile = save_join(downloadDir, packageDir, pyfile.name )
            
            # generate relative target filename
            targetfile = save_join(downloadDir, os.pathsep, targetfile)
            
            if exists( sourcefile ):
                if not exists( targetfile ):
                    # create target dir
                    targetpath = os.path.split(targetfile)[0]
                    if not exists(targetpath):
                        try:
                            os.makedirs(targetpath, 0755)
                        except:
                            pass
                    # rename and move file
                    move(sourcefile, targetfile)
                    # check if moved
                    if exists( targetfile ):
                        self.logInfo('Moved %(sourcefile)s to %(targetfile)s' % {'sourcefile': sourcefile, 'targetfile': targetfile})
                        # try to delete source dir if moved successfully
                        try:
                            os.rmdir(os.path.split(sourcefile)[0])
                        except OSError:
                            pass
                    else:
                        self.logInfo('Failed to move %(sourcefile)s to %(targetfile)s' % {'sourcefile': pyfile.name, 'targetfile': targetfile})
                else:
                    self.logWarning('File \'%(targetfile)s\' already exists. \'%(sourcefile)s\' will not be moved.' % {'sourcefile': pyfile.name, 'targetfile': targetfile})

