#!/bin/bash
PATH=/bin:/sbin:/usr/bin:/usr/sbin:/usr/local/bin:/usr/local/sbin:~/bin
export PATH

# 保存目录
save_dir="$HOME/ispip"
mkdir -p $save_dir

# APNIC源文件
apnic_ip_info="$save_dir/delegated-apnic-latest"
apnic_all_ip="$save_dir/cn_all_cidr.txt"

# 运营商输出文件
tel_file="$save_dir/telecom_cidr.txt"
uni_file="$save_dir/unicom_cidr.txt"
cmcc_file="$save_dir/mobile_cidr.txt"

# 清空旧文件
rm -f $apnic_ip_info $apnic_all_ip $tel_file $uni_file $cmcc_file

# 下载最新APNIC中国IP段
wget -q http://ftp.apnic.net/apnic/stats/apnic/delegated-apnic-latest -O $apnic_ip_info

# 提取中国IPv4、转换为标准CIDR
grep "apnic|CN|ipv4|" "$apnic_ip_info" | awk -F'|' '{print $4,$5}' | while read ip num;do
    cidr=$(echo "l($num)/l(2)" | bc -l | awk '{print 32-int($1)}')
    echo "${ip}/${cidr}"
done > $apnic_all_ip

# 按运营商分类
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

echo "==================== 网段采集完成 ===================="
echo "中国电信网段：$tel_file"
echo "中国联通网段：$uni_file"
echo "中国移动网段：$cmcc_file"
