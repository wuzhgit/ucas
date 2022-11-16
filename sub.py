"""
author: Les1ie
mail: me@les1ie.com
license: CC BY-NC-SA 3.0
"""
import os
import json
import pytz
import hashlib
import smtplib
import requests
from time import sleep
from pathlib import Path
from random import randint
from datetime import datetime
from email.utils import formataddr
from email.mime.text import MIMEText

# 开启debug将会输出打卡填报的数据，关闭debug只会输出打卡成功或者失败，如果使用github actions，请务必设置该选项为False
debug = False

# 忽略网站的证书错误，这很不安全 :(
verify_cert = True

# 全局变量，如果使用自己的服务器运行请根据需要修改 ->以下变量<-
user = "USERNAME"  # sep 账号
passwd = r"PASSWORD"  # sep 密码
api_key = "API_KEY"  # 可选， server 酱的通知 api key

# 可选，如果需要邮件通知，那么修改下面五行 :)
smtp_port = "SMTP_PORT"
smtp_server = "SMTP_SERVER"
sender_email = "SENDER_EMAIL"
sender_email_passwd = r"SENDER_EMAIL_PASSWD"
receiver_email = "RECEIVER_EMAIL"

# 全局变量，使用自己的服务器运行请根据需要修改 ->以上变量<-

# 如果检测到程序在 github actions 内运行，那么读取环境变量中的登录信息
if os.environ.get('GITHUB_RUN_ID', None):
    user = os.environ.get('SEP_USER_NAME', '')  # sep账号 aaa
    passwd = os.environ.get('SEP_PASSWD', '')  # sep密码
    api_key = os.environ.get('API_KEY', '')  # server酱的api，填了可以微信通知打卡结果，不填没影响

    smtp_port = os.environ.get('SMTP_PORT', '465')  # 邮件服务器端口，默认为qq smtp服务器端口
    smtp_server = os.environ.get('SMTP_SERVER', 'smtp.qq.com')  # 邮件服务器，默认为qq smtp服务器
    sender_email = os.environ.get('SENDER_EMAIL', 'example@example.com')  # 发送通知打卡通知邮件的邮箱
    sender_email_passwd = os.environ.get('SENDER_EMAIL_PASSWD', "password")  # 发送通知打卡通知邮件的邮箱密码
    receiver_email = os.environ.get('RECEIVER_EMAIL', 'example@example.com')  # 接收打卡通知邮件的邮箱


def login(s: requests.Session, username, password, cookie_file: Path):
    # r = s.get(
    #     "https://app.ucas.ac.cn/uc/wap/login?redirect=https%3A%2F%2Fapp.ucas.ac.cn%2Fsite%2FapplicationSquare%2Findex%3Fsid%3D2")
    # print(r.text)

    if cookie_file.exists():
        cookie = json.loads(cookie_file.read_text(encoding='utf-8'))
        s.cookies = requests.utils.cookiejar_from_dict(cookie)
        # 测试cookie是否有效
        if get_daily(s) == False:
            print("cookie失效，进入登录流程")
        else:
            print("cookie有效，跳过登录环节")
            return

    payload = {
        "username": username,
        "password": password
    }
    r = s.post("https://app.ucas.ac.cn/uc/wap/login/check", data=payload)

    # print(r.text)
    if r.json().get('m') != "操作成功":
        print("登录失败")
        message(api_key, sender_email, sender_email_passwd, receiver_email, "健康打卡登录失败", "登录失败")

    else:
        cookie_file.write_text(json.dumps(requests.utils.dict_from_cookiejar(r.cookies), indent=2), encoding='utf-8', )
        print("登录成功，cookies 保存在文件 {}，下次登录将优先使用cookies".format(cookie_file))


def get_daily(s: requests.Session):
    daily = s.get("https://app.ucas.ac.cn/ncov/api/default/daily?xgh=0&app_id=ucas")
    # info = s.get("https://app.ucas.ac.cn/ncov/api/default/index?xgh=0&app_id=ucas")
    if '操作成功' not in daily.text:
        # 会话无效，跳转到了登录页面
        print("会话无效")
        return False

    j = daily.json()
    return j.get('d') if j.get('d', False) else False


def submit(s: requests.Session, old: dict):
    new_daily = {
        'realname': old['realname'],
        'number': old['number'],

        "jzdz": "北京市石景山区玉泉路19号甲",     # Residential Address
        "zrzsdd": "2",                       # Yesterday place to stay    1.雁栖湖  8.京外
        # Whether you are in school or not  1.是, 主要是在雁栖湖校区   5.否
        "sfzx": "2",
        "szgj": "中国",                       # current country
        "szdd": "国内",                       # current address
        "dqszdd": "1",                       # current location

        #
        "address": "北京市怀石景山区",
        "area": "石景山区",
        "province": "北京市",
        "city": "",
      
        "geo_api_info": "{\"address\":\"北京市石景山区\",\"details\":\"玉泉路19号甲中国科学院大学玉泉路校区\",\"province\":{\"label\":\"北京市\",\"value\":\"\"},\"city\":{\"label\":\"\",\"value\":\"\"},\"area\":{\"label\":\"石景山区\",\"value\":\"\"}}",
        "szgj_api_info": "{\"area\":{\"label\":\"\",\"value\":\"\"},\"city\":{\"label\":\"\",\"value\":\"\"},\"address\":\"\",\"details\":\"\",\"province\":{\"label\":\"\",\"value\":\"\"}}",
        "szgj_select_info": {},
        #

        # whether you are in high or medium risk area or not  4. 无上述情况
        "dqsfzzgfxdq": "4",
        # do you have a travel history in risk area  4. 无上述情况
        "zgfxljs": "4",
        "tw": "1",                           # Today’s body temperature 1.37.2℃及以下
        # Do you have such symptoms as fever, fatigue, dry cough or difficulty in breathing today?
        "sffrzz": "0",
        "dqqk1": "1",                        # current situation      1.正常
        "dqqk1qt": "",
        "dqqk2": "1",                        # current situation      1.无异常
        "dqqk2qt": "",
        # 昨天是否接受核酸检测
        "sfjshsjc": "1",                     # PCR test?       1.是 0.否
        # 第一针接种
        "dyzymjzqk": "3",                    # first vaccination situation  3.已接种
        "dyzjzsj": "2021-03-27",             # date of first vaccination
        "dyzwjzyy": "",
        # 第二针接种
        "dezymjzqk": "3",                    # second vaccination situation  3.已接种
        "dezjzsj": "2021-04-21",             # date of second vaccination
        "dezwjzyy": "",
        # 第三针接种
        "dszymjzqk": "3",                    # third vaccination situation  6.未接种
        "dszjzsj": "2021-11-02",             # default time
        "dszwjzyy": "",            # reason of non-vaccination

        "gtshryjkzk": "1",                   # health situation
        "extinfo": "",                       # other information
        # personal information

        # "created_uid":"0",
        # "todaysfhsjc":"",
        # "is_daily":1,
        #"geo_api_infot": "{\"address\":\"北京市石景山区",\"details\":\"玉泉路19号甲中国科学院大学玉泉路校区\",\"province\":{\"label\":\"北京市\",\"value\":\"\"},\"city\":{\"label\":\"\",\"value\":\"\"},\"area\":{\"label\":\"石景山区\",\"value\":\"\"}}",

        "geo_api_infot": "{\"address\":\"北京市石景山区\",\"details\":\"玉泉路19号甲中国科学院大学玉泉路校区\",\"province\":{\"label\":\"北京市\",\"value\":\"\"},\"city\":{\"label\":\"\",\"value\":\"\"},\"area\":{\"label\":\"s石景山区\",\"value\":\"\"}}",
        # yesterday information
        "old_szdd": "国内",
        'old_city': old['old_city']
     
    }

    check_data_msg = check_submit_data(new_daily)  # 检查上报结果
    # if check_data_msg is not None:
    #     message(api_key, sender_email, sender_email_passwd, receiver_email, "每日健康打卡-{}".format(check_data_msg),
    #             "{}".format(new_daily))
    #     print("提交数据存在问题，请手动打卡，问题原因： {}".format(check_data_msg))
    #     return

    r = s.post("https://app.ucas.ac.cn/ncov/api/default/save", data=new_daily)
    if debug:
        from urllib.parse import parse_qs, unquote
        print("昨日信息:", json.dumps(old, ensure_ascii=False, indent=2))
        print("提交信息:",
              json.dumps(parse_qs(unquote(r.request.body), keep_blank_values=True), indent=2, ensure_ascii=False))

    result = r.json()
    if result.get('m') == "操作成功":
        print("打卡成功")
    else:
        print("打卡失败，错误信息: ", r.json().get("m"))

    message(api_key, sender_email, sender_email_passwd, receiver_email, result.get('m'), new_daily)


def check_submit_data(data: dict):
    """
    检查提交数据是否正常
    """
    msg = []
    # 所在地点
    if data['szdd'] != "国内":
        msg.append("所在地点不是国内，请手动填报")

    # 体温
    if int(data['tw']) > 4:
        msg.append("体温大于 37.3 度 ，请手动填报")

    if data['jrsflj'] == '是':
        msg.append("近日有离京经历，请手动填报")

    return ";".join(msg) if msg else None


def message(key, sender, mail_passwd, receiver, subject, msg):
    """
    再封装一下 :) 减少调用通知写的代码
    """
    if api_key != "":
        server_chan_message(key, subject, msg)
    if sender_email != "" and receiver_email != "":
        send_email(sender, mail_passwd, receiver, subject, msg)


def server_chan_message(key, title, body):
    """
    微信通知打卡结果
    """
    # 错误的key也可以发送消息，无需处理 :)
    msg_url = "https://sctapi.ftqq.com/{}.send?text={}&desp={}".format(key, title, body)
    requests.get(msg_url)


def send_email(sender, mail_passwd, receiver, subject, msg):
    """
    邮件通知打卡结果
    """
    try:
        body = MIMEText(str(msg), 'plain', 'utf-8')
        body['From'] = formataddr(["notifier", sender])
        body['To'] = formataddr(["me", receiver])
        body['Subject'] = "UCAS疫情填报助手通知-" + subject

        global smtp_port, smtp_server
        if smtp_server == "" or smtp_port == "":
            smtp_port = 465
            smtp_server = "smtp.qq.com"
        smtp = smtplib.SMTP_SSL(smtp_server, smtp_port)
        smtp.login(sender, mail_passwd)
        smtp.sendmail(sender, receiver, body.as_string())
        smtp.quit()
        print("邮件发送成功")
    except Exception as ex:
        print("邮件发送失败")
        if debug:
            print(ex)


def report(username, password):
    s = requests.Session()
    s.verify = verify_cert  # 不验证证书
    header = {
        "User-Agent": "Mozilla/5.0 (Linux; Android 10; AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 \
        Chrome/78.0.3904.62 XWEB/2693 MMWEBSDK/201201 Mobile Safari/537.36 MMWEBID/1300 \
        MicroMessenger/7.0.22.1820 WeChat/arm64 Weixin NetType/WIFI Language/zh_CN ABI/arm64"
    }
    s.headers.update(header)

    print(datetime.now(tz=pytz.timezone("Asia/Shanghai")).strftime("%Y-%m-%d %H:%M:%S %Z"))
    for i in range(randint(10,60),0,-1):
        print("\r等待{}秒后填报".format(i),end='')
        sleep(1)

    cookie_file_name = Path("{}.json".format(hashlib.sha512(username.encode()).hexdigest()[:8]))
    login(s, username, password, cookie_file_name)
    yesterday = get_daily(s)
    submit(s, yesterday)


if __name__ == "__main__":
    report(username=user, password=passwd)
