#!/usr/bin/env sh

pushd `dirname $0` > /dev/null
SCRIPTPATH=`pwd`
popd > /dev/null
PYTHONPATH=$PYTHONPATH:$SCRIPTPATH/lib/python2.7/

export PYTHONPATH && python Phoshare.py \
--export "/Volumes/Mac 1/iPhoto MBP" \
--iphoto "~/Pictures/iPhoto Library" \
--events ".*" \
--foldertemplate "{yyyy}/{mm}/{dd}/{name}" \
--nametemplate "{title}" \
--captiontemplate "{description}" \
--update \
--folderhints \
--facealbums \
--facealbum_prefix=FACES_ \
--face_keywords \
-f \
--gps \
#--dryrun
