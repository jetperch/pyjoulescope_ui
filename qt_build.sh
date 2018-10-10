#!/bin/bash

SCRIPT_DIR=`cd $( dirname "${BASH_SOURCE[0]}" ) && pwd`
TARGET_DIR=${SCRIPT_DIR}
UI_PATH=${SCRIPT_DIR}/joulescope_ui

usage() {
cat << EOF
usage: $0 [-h] [-o output_path]

Build the QT files into python code.

OPTIONS:
   -h      Show this message
   -o      The output directory

EOF
}

while getopts ":h:o:" OPTION; do
    case $OPTION in
        h)
            usage
            ;;
        o)
            TARGET_DIR=$OPTARG
            ;;
        ?)
            usage
            exit
            ;;
     esac
done

echo "Target ${TARGET_DIR}"
rm ${UI_PATH}/.gitignore

# Compile ui files from Qt Designer
for file in ${UI_PATH}/*.ui; do
    echo ${file}
    target=${file%.ui}.py
    target=${TARGET_DIR}/${target##${SCRIPT_DIR}}
    pyuic5 ${file} -o ${target} --from-imports
    echo ${target##*/} >> ${UI_PATH}/.gitignore
done

#compile resource file (icons, etc..)
for file in ${UI_PATH}/*.qrc; do
    echo ${file}
    target=${file%.qrc}_rc.py
    target=${TARGET_DIR}/${target##${SCRIPT_DIR}}
    pyrcc5 ${file} -o ${target}
    echo ${target##*/} >> ${UI_PATH}/.gitignore
done
