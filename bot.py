import yaml
import httpx
import os
import sys
import time
import subprocess
import sqlite3
import socket
from mcstatus.server import JavaServer
from flask import Flask, Blueprint, request
from typing import List, Dict

DATABASE_PATH = "data.db"
app = Flask(__name__)

class ServerConnectionError(Exception):
    pass

def init_database(admin_list):
    """初始化数据库，确保 bind 表存在，并将 admin_list 中的 qq 设置为管理员"""
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    # 创建 bind 表
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS bind (
            qq TEXT PRIMARY KEY NOT NULL,
            mc TEXT,
            is_admin BOOLEAN NOT NULL DEFAULT FALSE,
            ban BOOLEAN NOT NULL DEFAULT FALSE
        )
    """
    )

    # 将 admin_list 中的 qq 设置为管理员
    for qq in admin_list:
        cursor.execute(
            """
            INSERT OR REPLACE INTO bind (qq, is_admin) VALUES (?, TRUE)
        """,
            (qq,),
        )

    conn.commit()
    conn.close()


def add_bind(qq, mc):
    """添加绑定或更新现有绑定的 mc 值"""
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    try:
        # 如果 qq 不存在则插入新行，否则更新 mc
        cursor.execute(
            """
            INSERT INTO bind (qq, mc) VALUES (?, ?)
            ON CONFLICT(qq) DO UPDATE SET mc=excluded.mc
        """,
            (qq, mc),
        )

        conn.commit()
        return True
    except sqlite3.Error:
        conn.rollback()
        return False
    finally:
        conn.close()


def remove_bind(qq=None, mc=None):
    """
    移除指定 qq 或 mc 的绑定记录。
    :param qq: 要移除的 qq (可选)
    :param mc: 要移除的 mc (可选)
    :return: 是否成功移除记录
    """
    if not qq and not mc:
        raise ValueError("至少需要提供 qq 或 mc 进行删除")

    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    try:
        if qq:
            cursor.execute(
                """
                DELETE FROM bind WHERE qq = ?
            """,
                (qq,),
            )
        elif mc:
            cursor.execute(
                """
                DELETE FROM bind WHERE mc = ?
            """,
                (mc,),
            )

        conn.commit()
        return cursor.rowcount > 0
    except sqlite3.Error as e:
        print(f"删除操作时出错: {e}")
        conn.rollback()
        return False
    finally:
        conn.close()


def ban_bind(qq=None, mc=None):
    """将指定 qq 或 mc 的记录标记为封禁"""
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    try:
        if qq:
            cursor.execute(
                """
                UPDATE bind SET ban = TRUE WHERE qq = ?
            """,
                (qq,),
            )

        if mc:
            cursor.execute(
                """
                UPDATE bind SET ban = TRUE WHERE mc = ?
            """,
                (mc,),
            )

        conn.commit()
        return cursor.rowcount > 0
    except sqlite3.Error:
        conn.rollback()
        return False
    finally:
        conn.close()


def query_count(qq=None, mc=None):
    """
    查询数据的条目数量
    :param qq: 要查询的 qq (可选)
    :param mc: 要查询的 mc (可选)
    :return: 匹配的数据条目数量
    """
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    try:
        if qq:
            cursor.execute(
                """
                SELECT COUNT(*) FROM bind WHERE qq = ?
            """,
                (qq,),
            )
        elif mc:
            cursor.execute(
                """
                SELECT COUNT(*) FROM bind WHERE mc = ?
            """,
                (mc,),
            )
        else:
            raise ValueError("至少需要提供 qq 或 mc 进行查询")

        count = cursor.fetchone()[0]
        return count
    except sqlite3.Error as e:
        print(f"查询时出错: {e}")
        return 0
    finally:
        conn.close()

def query_username(qq=None):
    """
    查询数据的条目数量
    :param qq: 要查询的 qq
    :return: qq号对应的玩家名
    """
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    try:
        cursor.execute(
            """
            SELECT mc FROM bind WHERE qq = ?
        """,
            (qq,),
        )

        data = cursor.fetchone()[0]
        return data
    except sqlite3.Error as e:
        print(f"查询时出错: {e}")
        return 0
    finally:
        conn.close()


def force_edit_database(qq, mc):
    """
    修改数据库内容，根据传入的 qq 和 mc 更新数据。
    :param qq: 要更新的 qq
    :param mc: 要更新的 mc
    """
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    try:
        # 更新指定 qq 的 mc 值，或插入新记录
        cursor.execute(
            """
            INSERT INTO bind (qq, mc)
            VALUES (?, ?)
            ON CONFLICT(qq) DO UPDATE SET mc=excluded.mc
        """,
            (qq, mc),
        )

        conn.commit()
    except sqlite3.Error as e:
        print(f"数据库操作时出错: {e}")
    finally:
        conn.close()


def getMinecraftServerInfo(server_address: str) -> Dict:
    for i in range(5):
        try:
            server = JavaServer.lookup(server_address)
            status = server.status()
            players = server.query().players.names
            return {
                "version": status.version.name,
                "protocol_version": status.version.protocol,
                "players": players,
                "players_online": status.players.online,
                "players_max": status.players.max,
                "motd": status.description,
                "latency": round(status.latency, 2),
                "online": True,
                "error": False,
                "msg": "success"
            }
        except (TimeoutError, socket.gaierror) as e:
            return {
        "version": "N/A",
        "protocol_version": -1,
        "players": [],
        "players_online": -1,
        "players_max": -1,
        "motd": -1,
        "latency": -1,
        "online": False,
        "error": True,
        "msg": e
    }
    return {
        "version": "N/A",
        "protocol_version": -1,
        "players": [],
        "players_online": -1,
        "players_max": -1,
        "motd": -1,
        "latency": -1,
        "online": False,
        "error": False,
        "msg": "success"
    }


def query_ban(qq=None, mc=None):
    """
    检查指定 qq 或 mc 是否被封禁。
    :param qq: 要查询的 qq (可选)
    :param mc: 要查询的 mc (可选)
    :return: 如果有任何记录的 ban 列为 True，则返回 True，否则返回 False
    """
    if not qq and not mc:
        raise ValueError("至少需要提供 qq 或 mc 进行查询")

    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    try:
        query = ""
        params = ()

        if qq:
            query += """
                SELECT ban FROM bind WHERE qq = ?
            """
            params += (qq,)

        if mc:
            if query:
                query += " UNION "
            query += """
                SELECT ban FROM bind WHERE mc = ?
            """
            params += (mc,)

        cursor.execute(query, params)
        results = cursor.fetchall()

        # 检查是否有任何结果的 ban 列为 True
        for result in results:
            if result[0]:  # result[0] 是 ban 列的值
                return True

        return False
    except sqlite3.Error as e:
        print(f"查询时出错: {e}")
        return False
    finally:
        conn.close()


def addWhitelist(username: str):
    # 启动 Minecraft-Console-Client 并创建双向管道
    process = subprocess.Popen(
        ["MinecraftClient.exe", "cons01e3MU", "-", "mc.bili33.top:10125"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf8",
    )

    # 等待客户端启动
    time.sleep(3)

    # 发送消息
    process.stdin.write(f"!!awr add {username}\n")
    process.stdin.write("/quit\n")
    process.stdin.flush()
    output_all = ""
    # 读取并打印输出
    try:
        while True:
            output = process.stdout.readline()
            output_all += output
            if output == "":
                break
            print(output.strip())
    except Exception as e:
        print(f"读取输出时出错: {e}")

    # 等待进程结束
    process.wait()
    if not "已加入白名单" in output_all:
        raise ServerConnectionError("添加失败，请重试！")


def removeWhitelist(username: str):
    # 启动 Minecraft-Console-Client 并创建双向管道
    process = subprocess.Popen(
        ["MinecraftClient.exe", "cons01e3MU", "-", "mc.bili33.top:10125"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf8",
    )

    # 等待客户端启动
    time.sleep(3)

    # 发送消息
    process.stdin.write(f"!!awr remove {username}\n")
    process.stdin.write("/quit\n")
    process.stdin.flush()
    output_all = ""
    # 读取并打印输出
    try:
        while True:
            output = process.stdout.readline()
            output_all += output
            if output == "":
                break
            print(output.strip())
    except Exception as e:
        print(f"读取输出时出错: {e}")

    # 等待进程结束
    process.wait()
    if not "已从白名单移除" in output_all:
        raise ServerConnectionError("移除失败，请重试！")

debugBlueprint = Blueprint("debug", __name__, url_prefix="/debug")


@debugBlueprint.route("/minecraft/status/<qid>")
def statusHandler(qid: int):
    global server
    msg = f"""[CQ:at,qq={qid}] ====== 服务器状态一览 ======"""
    for serv in server:
        name = serv.get("name")
        host = serv.get("host")
        port = serv.get("port")
        status = getMinecraftServerInfo(f"{host}:{port}")
        if status.get("online"):
            singleMsg = f"""
            
服务器名称：{name}
延迟：{status.get("latency")} ms
在线人数：{status.get("players_online")}/{status.get("players_max")}
在线玩家：{str(status.get("players")).replace("[", "").replace("]", "").replace("'", "") if status.get("players") else "无"}
当前状态：在线"""
        elif status.get("error"):
            singleMsg = f"""
服务器名称：{name}            
当前状态：未知（{status.get("msg")}）"""
        else:
            singleMsg = f"""
            
服务器名称：{name}
当前状态：离线"""
        msg += singleMsg
    return msg


@debugBlueprint.route("/minecraft/addWhitelist")
def addWhitelistHandler(username=None):
    username = request.form.get("username")
    if not username:
        return "You must specifie a username!"


def helpHandler(qid: int):
    msg = f"""[CQ:at,qq={qid}] ====== EMUnion Bot 帮助信息 ======
● 使用 /status 查看服务器当前状态
● 使用 /bind <name> 来自助添加白名单
● 使用 /unbind 来解除QQ与白名单的绑定"""
    return msg


def bindHandler(msg: str, qid: int):
    split = msg.split(" ")
    if len(split) != 2:
        return f"[CQ:at,qq={qid}] 绑定命令正确用法：/bind <name>"
    elif not split[1].isascii():
        return f"[CQ:at,qq={qid}] 请输入正确的游戏名称！{split[1]} 不是合法的游戏名！"
    else:
        try:
            addWhitelist(split[1])
            add_bind(qid, split[1])
        except ServerConnectionError:
            f"[CQ:at,qq={qid}] 添加失败，无法连接到服务器，请重试！"
        return f"[CQ:at,qq={qid}] 已为玩家 {split[1]} 添加白名单！"


@app.route("/", methods=["POST"])
def mainHander():
    baseURL = f"http://{config.get('qq').get('host')}:{config.get('qq').get('port')}"
    data = request.json
    msgType = data.get("message_type")
    msg = data.get("raw_message")
    enable = True
    qid = data.get("sender").get("user_id")
    if data.get("raw_message") == "/status":
        try:
            msg = statusHandler(data.get("sender").get("user_id"))
        except Exception as e:
            msg = f"[CQ:at,qq={qid}] 无法获取服务器信息：{e}"
    elif data.get("raw_message") == "/help":
        msg = helpHandler(data.get("sender").get("user_id"))
    elif data.get("raw_message").startswith("/bind"):
        if len(msg.split(" ")) != 2:
            f"[CQ:at,qq={qid}] 绑定命令正确用法：/bind <name>"
        elif query_ban(qq=qid):
            msg = f"[CQ:at,qq={qid}] 你的QQ无法绑定账户，请联系管理员！"
        elif query_ban(mc=msg.split(" ")[1]):
            msg = f"[CQ:at,qq={qid}] 此用户名无法绑定，请联系管理员！"
        elif query_count(qq=qid):
            msg = f"[CQ:at,qq={qid}] 你已经拥有绑定的游戏ID了！本服务器一人一号，如有其他需要请联系管理员！"
        elif query_count(mc=msg.split(" ")[1]):
            msg = f"[CQ:at,qq={qid}] 此用户名 {msg.split(' ')[1]} 已经被绑定！请联系管理员！"
        else:
            msg = bindHandler(
                data.get("raw_message"), data.get("sender").get("user_id")
            )
    elif data.get("raw_message") == "/unbind":
        if remove_bind(data.get("sender").get("user_id")):
            username = query_username
            removeWhitelist(username)
            remove_bind(mc=username)
            msg = f"[CQ:at,qq={qid}] 已经为你解除 {username} 的绑定！"
        else:
            msg = f"[CQ:at,qq={qid}] 解除绑定失败！请联系管理员！"
    elif data.get("raw_message").startswith("/admin"):
        commands = data.get("raw_message").split(" ")
        if qid not in admin:
            msg = f"[CQ:at,qq={qid}] 你不在bot管理员列表内！"
        elif len(commands) == 1:
            msg = f"""[CQ:at,qq={qid}] ====== 管理员命令列表 ======
● 使用/admin bind <QQ> <name> 来为玩家强制绑定
● 使用/admin unbind <name> 来为玩家强制接触绑定
● 使用/admin ban <name> 来封禁一名玩家"""
        elif commands[1] == "bind":
            if len(commands) != 4 or not commands[2].isdigit() or not commands[3].isascii():
                msg = (
                    f"[CQ:at,qq={qid}] 管理员命令/admin bind <QQ> <name>，请正确使用！"
                )
            else:
                addWhitelist(commands[3])
                force_edit_database(commands[2], commands[3])
                msg = f"[CQ:at,qq={qid}] 已经为 {commands[2]} 添加了用户名 {commands[3]} 的绑定！"
        elif commands[1] == "unbind":
            if len(commands) != 3 or not commands[2].isascii():
                msg = f"[CQ:at,qq={qid}] 管理员命令/admin unbind <name>，请正确使用！"
            else:
                removeWhitelist(commands[2])
                remove_bind(mc=commands[2])
                msg = f"[CQ:at,qq={qid}] 已经清除了用户名 {commands[3]} 的绑定！"
        elif commands[1] == "ban":
            if len(commands) != 3 or not commands[2].isascii():
                msg = f"[CQ:at,qq={qid}] 管理员命令/admin ban <name>，请正确使用！"
            else:
                removeWhitelist(commands[2])
                ban_bind(mc=commands[2])
                msg = f"[CQ:at,qq={qid}] 已经封禁了用户名为 {commands[3]} 的玩家！"
    else:
        enable = False
    if enable:
        if msgType == "group":
            response = httpx.post(
                baseURL + "/send_msg",
                params={
                    "message_type": "group",
                    "group_id": data.get("group_id"),
                    "message": msg,
                },
            )
        elif msgType == "private":
            response = httpx.post(
                baseURL + "/send_msg",
                params={
                    "message_type": "private",
                    "user_id": data.get("sender").get("user_id"),
                    "message": msg,
                },
            )
    return "success"


class args:
    def __init__(self):
        self.offline_name = "cons01e3MU"
        self.auth = False
        self.session_name = None


if __name__ == "__main__":
    # 检查 config.yml 是否存在
    if not os.path.exists("config.yml"):
        print("Error: config.yml not found. Please provide the configuration file.")
        sys.exit(1)

    # 检查 MinecraftClient.exe 是否存在
    if not os.path.exists("MinecraftClient.exe"):
        print("Error: MinecraftClient.exe not found. Please download it from https://github.com/MCCTeam/Minecraft-Console-Client/releases")
        sys.exit(1)

    # 读取配置文件
    with open("config.yml", "r", encoding="utf-8") as file:
        config = yaml.safe_load(file)

    admin = config.get("admin", [])
    server = config.get("servers")
    init_database(admin)
    app.register_blueprint(debugBlueprint)
    app.run(host="0.0.0.0", port=9999, debug=True)