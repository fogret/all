#!/bin/bash
PATH=/bin:/sbin:/usr/bin:/usr/sbin:/usr/local/bin:/usr/local/sbin:~/bin
export PATH

save_dir="./ispip"
mkdir -p $save_dir

apnic_ip_info="$save_dir/delegated-apnic-latest"
apnic_all_ip="$save_dir/cn_all_cidr.txt"
tel_file="$save_dir/telecom_cidr.txt"
uni_file="$save_dir/unicom_cidr.txt"
cmcc_file="$save_dir/mobile_cidr.txt"

rm -f $apnic_ip_info $apnic_all_ip $tel_file $uni_file $cmcc_file

wget -q http://ftp.apnic.net/apnic/stats/apnic/delegated-apnic-latest -O $apnic_ip_info

grep "apnic|CN|ipv4|" "$apnic_ip_info" | awk -F'|' '{print $4,$5}' | while read ip num;do
    cidr=$(echo "l($num)/l(2)" | bc -l | awk '{print 32-int($1)}')
    echo "${ip}/${cidr}"
done > $apnic_all_ip

while read line
do
isp_ip=$(echo $line | awk -F'/' '{print $1}')
isp_info=$(whois -h whois.apnic.net $isp_ip | grep -E "mnt-|netname" | awk '{print $2}' | xargs)

if echo $isp_info | grep -qiE "CNC|UNICOM";then
    echo "$line" >> $uni_file
elif echo $isp_info | grep -qiE "CHINANET|TELECOM|BJTEL";then
    echo "$line" >> $tel_file
elif echo $isp_info | grep -qiE "CMCC|CMNET";then
    echo "$line" >> $cmcc_file
fi
done < $apnic_all_ip
