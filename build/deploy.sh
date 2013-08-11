cd `dirname $0`/../src

OLD=`cat ./addon.xml | grep '<addon' | grep 'version="' | grep -E -o 'version="[0-9\.]+"' |  grep -E -o '[0-9\.]+'`
echo "Old version: $OLD"
echo -n 'New version: '
read NEW

sed -e "s/version=\"$OLD\"/version=\"$NEW\"/g" ./addon.xml > ./addon2.xml
mv ./addon2.xml ./addon.xml

rm -rf ../plugin.rutracker
rm -f ./plugin.rutracker.zip
mkdir ../plugin.rutracker
cp -r ./* ../plugin.rutracker/

cd ../
zip -rq ./plugin.rutracker.zip ./plugin.rutracker

cp ./plugin.rutracker.zip ../repository.hal9000/repo/plugin.rutracker/plugin.rutracker-$NEW.zip

rm -rf ./plugin.rutracker
rm -f ./plugin.rutracker.zip

`../repository.hal9000/build/build.sh`
