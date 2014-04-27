# IcefilmsShowSyncer pyLoad plugin

Original version from [forum.pyload.org (german)](http://forum.pyload.org/viewtopic.php?f=9&t=1192 "forum.pyload.org German Thread"). 
Development stopped in 2012 so this is the revived version of the pyload plugin. 
The software is provided under the GPL v3 so feel free to fork or be so kind and issue pull requests for your custom feature / fixes. 

## Features:

*   checks local storeage for missing episodes/seasons on hardrive and searches for missing on icefilms.info
*   creates a package for every series containing the links
*   on finished downloads renames and moves episodes to folder location
*   gets invoked periodically, default 12 hours. Therefore getting new content is blazingly fast, without the need to add links manually.
*   plugin configurable via web-ui
*   setting up Series is done via ini-configuration on filesystem. Simple texteditor is sufficient.
*   preferred hoster configurable
*   preferred quality configurable

## Requirements:
*  working install of [pyLoad](http://pyload.org/)

## Installation:
1. Download [IcefilmsShowSyncer.zip](https://github.com/t4skforce/IcefilmsShowSyncer/archive/master.zip) 
2. Extract IcefilmsShowSyncer.zip unzip,7zip
3. Copy file icefilmsShowSyncer.py to `<pyload install dir>/module/plugins/hooks/`
4. Copy file icefilmsShowSyncer.conf to .pyload/ (pyload config folder)
5. Optional edit icefilmsShowSyncer.conf
6. Restart pyload (service pyload restart)
7. Open WebUi => Config => Plugins => IcefilmsShowSyncer
8. Enable plugin via setting Activated: on

## Konfiguration:
The plugin is configured via two locations.


###  Web-Ui

Web-Ui => Config => Plugins => IcefilmsShowSyncer

*   Naming scheme (used by 'rename and move')
*   Check interval in hours
*   Activated
*   Move new episodes directly to queue
*   Config file specifying all shows to sync
*   Rename and move downloaded file to series dir
*   comma-separated list of preferred file hosters: (eg.: movreel)
*   Directory containing all series subdirectories

###  File Config
File `/home/user/.pyload/icefilmsShowSyncer.conf`.

This config file contains your series information. It defines what sereies the plugin should look out for.

```
[Misfits]
active = 1
hdPreferred = 0
url = http://www.icefilms.info/tv/series/2/1341
excludedEpisodes = S02E00 S02E04
excludedSeasons = 1 3
```

**[Misfits]**

	Name of the series folder (`<base_download_folder pyload>/<plugin "Directory containing all series subdirectories">/Misfits`)
	
**active**

	enable/disable series download
	  
	  
**hdPreferred**

	define if hd download is preferred
	
	
**url** 

	url of series page on icefilms.info
	
	
**excludedEpisodes** 

	exclude specified episodes
	
	
**excludedSeasons** 

	exclude whole season


Example is shipped with 2 series configs.

## Info

*  When adding a lot of episodes it can take some time until all the download links are found (please give it some time)
*  Plugin only adds missing Episodes. If you already got it downloaded or it is not allowed to download via `excludedEpisodes` or `excludedSeasons` the inks will not be added
*  When canging the icefilmsShowSyncer.conf file eather restart pyload or disable and reenable the plugin in pyload 
*  If something is not working, please create an issue on [github](https://github.com/t4skforce/IcefilmsShowSyncer/issues "Issues") and provide complete log of pyload in debug mode

## Changelog

Version 0.6:
   *   Fixed issue with "No download Id found for ..."
   *   changed default behavior of "Directory containing all series subdirectories" which now is a forced subdirectory of <base_download_folder pyload>