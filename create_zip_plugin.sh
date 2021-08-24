#!/bin/bash
plugin_dir=$( basename $( pwd ) )
if [ -f "./$plugin_dir.zip" ]; then
  rm "./$plugin_dir.zip"
fi
mkdir "./$plugin_dir"
cp *.py "./$plugin_dir"
mkdir "./$plugin_dir/i18n"
cp ./i18n/*.qm "./$plugin_dir/i18n"
mkdir "./$plugin_dir/resources"
cp ./resources/* "./$plugin_dir/resources"
for item in metadata.txt LICENSE; do cp "./$item" "./$plugin_dir"; done
zip -r $plugin_dir $plugin_dir
rm -r $plugin_dir
#
kdialog --msgbox "Zip file created: "$plugin_dir".zip"
