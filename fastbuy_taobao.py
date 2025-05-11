##################################################################################################################
# 淘宝抢购脚本                                                                                                   #
# 使用方法：                                                                                                     #
#     1、先将需要抢购的商品放到购物车中（注意购物车中只能放需要抢购的东西，到时抢购的时候会全部提交）；                   #            
#     2、执行此脚本，然后等待浏览器打开弹出登陆界面，手机淘宝扫描登陆；                                               #
#     3、脚本开始执行后，会定时刷新防止超时退出，到了设定时间点会自动尝试提交订单；                                    #
#     4、抢购时为了防止一次网络拥堵出问题，设置了尝试机制，会不停尝试提交订单，直到提交成功或达到最大重试次数为止        #
#     5、脚本只负责提交订单，之后24小时内需要自行完成付款操作。                                                     #
##################################################################################################################
import os
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import datetime
import time
import random
from selenium.common.exceptions import TimeoutException
import requests
import json
import threading


# ==== 抢购设置参数区域 ====
BUY_TIME = input("请输入抢购时间（格式：2025-05-09 23:50:00）：")
# 控制复选框处理
CHECK_AGREEMENT_CHECKBOX = False  # 是否检查并点击同意协议复选框
# 最大重试次数
MAX_RETRY_TIMES = 100  # 抢购重试次数上限
# 抢购超时时间(分钟)
PURCHASE_TIMEOUT_MINUTES = 5  # 总的抢购尝试时间上限
# 是否在提交订单成功后播放声音提醒
PLAY_SOUND_ON_SUCCESS = True  # 如需启用声音提醒，将此处改为True


# ====  标识登录状态、重试次数 ====
MAX_LOGIN_RETRY_TIMES = 6

current_retry_login_times = 0
login_success = False
buy_time_object = datetime.datetime.strptime(BUY_TIME, "%Y-%m-%d %H:%M:%S")

# 添加服务器时间校准相关的全局变量
SERVER_TIME_API = "https://f.m.suning.com/api/ct.do"  # 苏宁易购时间API
time_offset = 0  # 本地时间与服务器时间的偏移量(毫秒)
server_time_synced = False  # 是否已与服务器时间同步

# 添加获取服务器时间的函数
def sync_with_server_time():
    """同步本地时间与服务器时间，计算时间偏移"""
    global time_offset, server_time_synced
    
    try:
        # 在发送请求前记录本地时间
        local_time_before = int(time.time() * 1000)
        
        # 请求苏宁易购时间API
        response = requests.get(SERVER_TIME_API, timeout=3)
        
        # 请求完成后再次记录本地时间
        local_time_after = int(time.time() * 1000)
        
        # 计算大致的网络延迟（单向）
        network_delay = (local_time_after - local_time_before) // 2
        
        # 解析响应
        if response.status_code == 200:
            data = response.json()
            if data["code"] == "1":
                # 获取服务器时间（毫秒）
                server_timestamp = data["currentTime"]
                
                # 计算本地时间与服务器时间的偏移量，考虑网络延迟
                local_time_middle = (local_time_before + local_time_after) // 2
                time_offset = server_timestamp - local_time_middle
                
                # 打印时间同步信息
                local_datetime = datetime.datetime.fromtimestamp(local_time_middle / 1000)
                server_datetime = datetime.datetime.fromtimestamp(server_timestamp / 1000)
                
                print(f"[时间同步] 本地时间: {local_datetime}")
                print(f"[时间同步] 服务器时间: {server_datetime}")
                print(f"[时间同步] 时间偏移量: {time_offset} 毫秒")
                print(f"[时间同步] 估计网络延迟: {network_delay} 毫秒")
                
                server_time_synced = True
                return True
            else:
                print(f"[时间同步] 服务器返回错误代码: {data['code']}")
        else:
            print(f"[时间同步] HTTP请求失败，状态码: {response.status_code}")
    
    except Exception as e:
        print(f"[时间同步] 同步服务器时间出错: {repr(e)}")
    
    print("[时间同步] 无法同步服务器时间，将使用本地时间")
    return False


# 添加获取当前校准时间的函数
def get_adjusted_time():
    """获取经过校准的当前时间"""
    if server_time_synced:
        # 获取当前本地时间戳（毫秒）
        current_local_time = int(time.time() * 1000)
        # 应用偏移量
        adjusted_time = current_local_time + time_offset
        # 转换为datetime对象
        return datetime.datetime.fromtimestamp(adjusted_time / 1000)
    else:
        # 如果未同步，返回本地时间
        return datetime.datetime.now()


now_time = get_adjusted_time()
if now_time > buy_time_object:
    print("当前已过抢购时间，请确认抢购时间是否填错...")
    exit(0)

print("正在打开chrome浏览器...")
# 让浏览器不要显示当前受自动化测试工具控制的提醒
option = webdriver.ChromeOptions()
option.add_argument("disable-infobars")
option.add_argument('--ignore-certificate-errors')
option.add_argument('--ignore-ssl-errors')
option.add_experimental_option('excludeSwitches', ['enable-logging']) # 尝试减少控制台日志量
driver = webdriver.Chrome(options=option)
driver.maximize_window()
print("chrome浏览器已经打开...")


def __login_operates():
    driver.get("https://www.taobao.com")
    try:
        if driver.find_element(By.LINK_TEXT, "亲，请登录"):
            print("没登录，开始点击登录按钮...")
            driver.find_element(By.LINK_TEXT, "亲，请登录").click()
            print("请使用手机淘宝扫描屏幕上的二维码进行登录...")
            time.sleep(10)
    except:
        print("已登录，开始执行跳转...")
        global login_success
        global current_retry_login_times
        login_success = True
        current_retry_login_times = 0


def login():
    print("开始尝试登录...")
    __login_operates()
    global current_retry_login_times
    while current_retry_login_times < MAX_LOGIN_RETRY_TIMES:
        current_retry_login_times = current_retry_login_times + 1
        print("当前尝试登录次数：" + str(current_retry_login_times))
        __login_operates()
        if login_success:
            print("登录成功")
            break
        else:
            print("等待登录中...")

    if not login_success:
        print("规定时间内没有扫码登录淘宝成功，执行失败，退出脚本!!!")
        exit(0)

    now = get_adjusted_time()
    print("login success:", now.strftime("%Y-%m-%d %H:%M:%S"))
    
    # 登录成功后，立即同步服务器时间
    print("正在同步服务器时间...")
    sync_with_server_time()
    
    # 每隔10分钟重新同步一次，确保时间偏移量准确
    threading.Timer(600, sync_with_server_time).start()


def __refresh_keep_alive():
    # 重新加载购物车页面，定时操作，防止长时间不操作退出登录
    driver.get("https://cart.taobao.com/cart.htm")
    print("刷新购物车界面，防止登录超时...")
    time.sleep(60)


def keep_login_and_wait():
    print("当前距离抢购时间点还有较长时间，开始定时刷新防止登录超时...")
    while True:
        # 使用校准后的时间
        currentTime = get_adjusted_time()
        if (buy_time_object - currentTime).total_seconds() > 180:
            __refresh_keep_alive()
            # 每次刷新页面后同步服务器时间
            sync_with_server_time()
        else:
            print("抢购时间点将近，停止自动刷新，准备进入抢购阶段...")
            # 临近抢购前再次同步时间
            sync_with_server_time()
            break


def play_success_sound():
    if PLAY_SOUND_ON_SUCCESS:
        try:
            import winsound
            # 播放系统提示音，提醒用户订单已提交成功
            winsound.Beep(800, 500)  # 频率800Hz，持续500毫秒
            time.sleep(0.2)
            winsound.Beep(1000, 500)  # 频率1000Hz，持续500毫秒
            print("已播放成功提示音")
        except:
            print("播放提示音失败，可能不支持此功能")


# 添加全局变量存储提交按钮
submit_order_button = None
order_submit_page_loaded = False

# 添加提前准备时间设置（抢购时间前多少分钟开始准备）
PREPARE_MINUTES_BEFORE = 2  # 抢购时间前2分钟开始准备

# 添加重试间隔设置
RETRY_INTERVAL_SECONDS = 0.5  # 重试间隔0.5秒

# 在文件顶部添加一个全局变量来控制重试不同点击方法的顺序
CLICK_METHODS = ["normal", "js", "actions", "offset", "wait_and_retry"]

# 记录已知有效的提交按钮选择器，避免每次重新尝试所有可能的选择器
LAST_WORKING_SELECTOR = None
# 用于直接提交表单的JavaScript代码
FORM_SUBMIT_JS = """
(function() {
    // 尝试多种方式触发提交
    // 1. 查找提交订单按钮并点击
    var buttons = document.querySelectorAll('a[href*="submit"], button[type="submit"], button:contains("提交订单"), .submit-btn, #submitOrderPC_1, .go-btn');
    for(var i=0; i<buttons.length; i++) {
        if(buttons[i].offsetParent !== null && buttons[i].innerText.indexOf('提交') >= 0) {
            console.log("找到按钮元素: ", buttons[i]);
            buttons[i].click();
            return true;
        }
    }
    
    // 2. 查找订单表单并直接提交
    var forms = document.forms;
    for(var i=0; i<forms.length; i++) {
        if(forms[i].action && (forms[i].action.indexOf('buy') >= 0 || forms[i].action.indexOf('order') >= 0)) {
            console.log("直接提交表单: ", forms[i]);
            forms[i].submit();
            return true;
        }
    }
    
    // 3. 创建submit事件
    var submitEvt = new Event('submit', {bubbles:true, cancelable:true});
    var found = false;
    document.querySelectorAll('form').forEach(function(form) {
        form.dispatchEvent(submitEvt);
        found = true;
    });
    
    return found;
})();
"""

def prepare_for_purchase():
    """提前完成结算步骤，识别提交订单按钮，持续尝试直到成功"""
    global submit_order_button, order_submit_page_loaded
    
    print("开始提前准备抢购环节...")
    prepare_start_time = get_adjusted_time()  # 使用校准时间
    
    # 计算最晚准备截止时间（抢购前10秒）
    latest_prepare_time = buy_time_object - datetime.timedelta(seconds=10)
    prepare_success = False
    
    # 跟踪连续失败次数
    consecutive_failures = 0
    current_method_index = 0
    
    # 持续尝试直到成功或达到最晚准备时间
    while not prepare_success and get_adjusted_time() < latest_prepare_time:
        try:
            # 打开购物车
            driver.get("https://cart.taobao.com/cart.htm")
            print(f"[{get_adjusted_time()}] 加载购物车页面...")
            time.sleep(1)  # 等待页面加载
            
            # 尝试滚动到页面顶部，确保视图正确
            driver.execute_script("window.scrollTo(0, 0);")
            time.sleep(0.5)
            
            # 点击购物车里全选按钮
            try:
                select_all_button = WebDriverWait(driver, 10).until(
                    EC.element_to_be_clickable((By.XPATH, "//div[contains(@class, 'cart-select-all') or @id='J_SelectAll1']//input[@type='checkbox'] | //label[contains(.,'全选')]"))
                )
                if not select_all_button.is_selected():
                    select_all_button.click()
                print(f"[{get_adjusted_time()}] 已选中购物车中全部商品")
            except Exception as e:
                print(f"[{get_adjusted_time()}] 无法找到或点击全选按钮: {e}")
                driver.save_screenshot(f"error_select_all_{get_adjusted_time().strftime('%H%M%S')}.png")
                consecutive_failures += 1
                if consecutive_failures >= 3:
                    # 如果连续失败3次，刷新页面
                    driver.refresh()
                    time.sleep(2)
                    consecutive_failures = 0
                continue  # 继续下一次重试
            
            # 尝试点击结算按钮 - 使用多种方法轮流尝试
            print(f"[{get_adjusted_time()}] 尝试点击结算按钮 (使用方法: {CLICK_METHODS[current_method_index]})...")
            
            # 首先定位结算按钮
            try:
                checkout_button = WebDriverWait(driver, 5).until(
                    EC.presence_of_element_located((By.XPATH, "//*[@id='settlementContainer_1']/div[4]/div/div[2] | //div[@id='J_Go'] | //a[contains(text(), '结 算')] | //button[contains(text(), '结 算')]"))
                )
                
                # 确保元素在视图中
                driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", checkout_button)
                time.sleep(0.5)
                
                # 根据当前尝试的方法来点击
                click_method = CLICK_METHODS[current_method_index]
                
                if click_method == "normal":
                    # 尝试普通点击
                    WebDriverWait(driver, 5).until(
                        EC.element_to_be_clickable((By.XPATH, "//*[@id='settlementContainer_1']/div[4]/div/div[2] | //div[@id='J_Go'] | //a[contains(text(), '结 算')] | //button[contains(text(), '结 算')]"))
                    ).click()
                
                elif click_method == "js":
                    # 使用JavaScript点击
                    driver.execute_script("arguments[0].click();", checkout_button)
                
                elif click_method == "actions":
                    # 使用Actions链模拟点击
                    actions = ActionChains(driver)
                    actions.move_to_element(checkout_button).click().perform()
                
                elif click_method == "offset":
                    # 尝试点击元素中心偏上的位置，避开可能的覆盖元素
                    actions = ActionChains(driver)
                    actions.move_to_element_with_offset(checkout_button, 0, -5).click().perform()
                
                elif click_method == "wait_and_retry":
                    # 等待更长时间再尝试点击
                    time.sleep(2)
                    driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                    time.sleep(1)
                    driver.execute_script("window.scrollTo(0, 0);")
                    time.sleep(1)
                    WebDriverWait(driver, 8).until(
                        EC.element_to_be_clickable((By.XPATH, "//*[@id='settlementContainer_1']/div[4]/div/div[2] | //div[@id='J_Go'] | //a[contains(text(), '结 算')] | //button[contains(text(), '结 算')]"))
                    ).click()
                
                print(f"[{get_adjusted_time()}] 已点击结算按钮，等待订单确认页面...")
                time.sleep(2)  # 等待页面加载
                
                # 检查URL变化以确认是否进入了结算页面
                current_url = driver.current_url
                if "buy.taobao.com" in current_url or "buy.tmall.com" in current_url:
                    print(f"[{get_adjusted_time()}] 成功进入订单确认页面: {current_url}")
                    consecutive_failures = 0  # 重置连续失败计数
                else:
                    print(f"[{get_adjusted_time()}] 点击结算后URL未变化，可能未成功进入订单页面: {current_url}")
                    raise Exception("点击结算后未成功跳转")
                
            except Exception as e:
                print(f"[{get_adjusted_time()}] 点击结算按钮失败: {e}")
                
                # 保存截图分析问题
                driver.save_screenshot(f"click_error_{click_method}_{get_adjusted_time().strftime('%H%M%S')}.png")
                
                # 尝试下一种点击方法
                current_method_index = (current_method_index + 1) % len(CLICK_METHODS)
                consecutive_failures += 1
                
                # 如果所有方法都尝试失败，短暂等待后重试
                if consecutive_failures >= len(CLICK_METHODS) * 2:
                    print(f"[{get_adjusted_time()}] 多种点击方法均失败，等待后重新加载页面...")
                    time.sleep(RETRY_INTERVAL_SECONDS)
                    consecutive_failures = 0
                continue  # 继续下一次重试
            
            # 处理同意协议复选框
            if CHECK_AGREEMENT_CHECKBOX:
                try:
                    agree_checkbox_xpath = "//*[@id='submitOrderPC_1']/div/div/label/input | //input[contains(@id, 'agreement')] | //input[@type='checkbox'][contains(@id, 'agree')]"
                    agree_checkbox = WebDriverWait(driver, 5).until(
                        EC.element_to_be_clickable((By.XPATH, agree_checkbox_xpath))
                    )
                    
                    if not agree_checkbox.is_selected():
                        agree_checkbox.click()
                        print(f"[{get_adjusted_time()}] 已勾选同意协议复选框")
                    else:
                        print(f"[{get_adjusted_time()}] 同意协议复选框已被勾选")
                except Exception as e:
                    print(f"[{get_adjusted_time()}] 处理同意协议复选框时出错: {e}")
                    # 仍继续尝试后续操作，因为有些页面可能没有这个复选框
            
            # 提前定位提交订单按钮
            print(f"[{get_adjusted_time()}] 尝试定位提交订单按钮...")
            submit_button_xpaths = [
                "//a[contains(text(),'提交订单')] | //button[contains(text(),'提交订单')]",
                "//*[@id='submitOrder']/div/div[2]/div",
                "//div[contains(@class,'submit-btn')] | //button[contains(@class,'submit')]",
                "//a[@id='submitOrderPC_1'] | //button[@id='submitOrderPC_1']"
            ]
            
            button_found = False
            for xpath in submit_button_xpaths:
                try:
                    submit_order_button = WebDriverWait(driver, 3).until(
                        EC.presence_of_element_located((By.XPATH, xpath))
                    )
                    
                    # 确保按钮可见
                    driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", submit_order_button)
                    time.sleep(0.5)
                    
                    # 确认按钮可点击
                    if submit_order_button.is_displayed() and submit_order_button.is_enabled():
                        print(f"[{get_adjusted_time()}] 成功找到可点击的提交订单按钮，使用XPath: {xpath}")
                        order_submit_page_loaded = True
                        button_found = True
                        driver.save_screenshot(f"submit_button_found_{get_adjusted_time().strftime('%H%M%S')}.png")
                        break
                except Exception as e:
                    continue
            
            if button_found:
                print(f"[{get_adjusted_time()}] 提前准备成功！已找到提交订单按钮")
                prepare_success = True
                break
            else:
                print(f"[{get_adjusted_time()}] 未找到提交订单按钮，将重试准备过程")
                driver.save_screenshot(f"submit_button_not_found_{get_adjusted_time().strftime('%H%M%S')}.png")
                time.sleep(RETRY_INTERVAL_SECONDS)
                
        except Exception as e:
            print(f"[{get_adjusted_time()}] 准备过程中发生错误: {repr(e)}")
            driver.save_screenshot(f"prepare_error_{get_adjusted_time().strftime('%H%M%S')}.png")
            consecutive_failures += 1
            time.sleep(RETRY_INTERVAL_SECONDS)
        
        # 在循环中定期再次同步服务器时间
        if random.random() < 0.05:  # 约5%的循环迭代会同步时间
            sync_with_server_time()
    
    prepare_duration = (get_adjusted_time() - prepare_start_time).total_seconds()  # 使用校准时间
    print(f"[{get_adjusted_time()}] 提前准备过程耗时 {prepare_duration:.2f} 秒，结果: {'成功' if prepare_success else '失败'}")
    return prepare_success


def execute_purchase():
    """在抢购时间准确点击提交订单按钮，失败后持续尝试"""
    global submit_order_button, order_submit_page_loaded, LAST_WORKING_SELECTOR
    
    submit_succ = False
    retry_submit_times = 0
    purchase_timeout = get_adjusted_time() + datetime.timedelta(minutes=PURCHASE_TIMEOUT_MINUTES)
    current_click_method = 0
    
    # 记录订单确认页面URL，用于刷新
    order_page_url = None
    
    # 在抢购开始前，最后一次同步服务器时间
    if get_adjusted_time() < buy_time_object:
        print("抢购即将开始，最后同步服务器时间...")
        sync_with_server_time()
    
    while get_adjusted_time() < purchase_timeout and retry_submit_times < MAX_RETRY_TIMES:
        now = get_adjusted_time()
        
        # 检查是否到了抢购时间
        if now >= buy_time_object:
            print(f"[{now}] 到达抢购时间，执行抢购...尝试次数：{retry_submit_times + 1}")
            retry_submit_times += 1
            
            try:
                # 如果在订单页面
                current_url = driver.current_url
                if ("buy.taobao.com" in current_url or "buy.tmall.com" in current_url) and "order_detail" not in current_url:
                    # 保存当前页面URL
                    if not order_page_url:
                        order_page_url = current_url
                        print(f"[{now}] 记录订单页面URL: {order_page_url}")
                    
                    # 尝试多种高效提交方式
                    # 方式1: 直接使用JavaScript执行表单提交
                    print(f"[{now}] 尝试使用JavaScript直接提交订单...")
                    submit_result = driver.execute_script(FORM_SUBMIT_JS)
                    if submit_result:
                        print(f"[{now}] JavaScript执行订单提交成功")
                    
                    # 方式2: 如果有已知的有效选择器，直接使用
                    if not submit_result and LAST_WORKING_SELECTOR:
                        try:
                            print(f"[{now}] 尝试使用上次有效的选择器: {LAST_WORKING_SELECTOR}")
                            elem = driver.find_element(By.CSS_SELECTOR, LAST_WORKING_SELECTOR)
                            if elem and elem.is_displayed() and elem.is_enabled():
                                driver.execute_script("arguments[0].click();", elem)
                                print(f"[{now}] 使用缓存选择器点击成功")
                                submit_result = True
                        except:
                            # 如果失败，继续尝试其他方法
                            pass
                    
                    # 方式3: 如果前两种方式都失败，使用更精确的选择器
                    if not submit_result:
                        # 使用更精确的CSS选择器，比XPath更快
                        css_selectors = [
                            "a.go-btn", 
                            "button.go-btn", 
                            "button.submit-btn", 
                            "a.submit-btn",
                            "#submitOrderPC_1",
                            "button[type='submit']",
                            "[class*='submit'][class*='btn']"
                        ]
                        
                        for selector in css_selectors:
                            try:
                                elems = driver.find_elements(By.CSS_SELECTOR, selector)
                                for elem in elems:
                                    if elem.is_displayed() and elem.is_enabled() and "提交" in elem.text:
                                        print(f"[{now}] 找到提交按钮，使用选择器: {selector}")
                                        # 缓存有效的选择器供下次使用
                                        LAST_WORKING_SELECTOR = selector
                                        # 使用JS点击，更可靠
                                        driver.execute_script("arguments[0].click();", elem)
                                        print(f"[{now}] 精确定位后点击提交按钮")
                                        submit_result = True
                                        break
                            except:
                                continue
                            
                            if submit_result:
                                break
                    
                    # 方式4: 快速键盘操作模拟表单提交
                    if not submit_result:
                        try:
                            print(f"[{now}] 尝试使用键盘快捷键提交...")
                            # 发送Tab键切换焦点到提交按钮
                            # 这种方法在某些页面上很有效
                            for _ in range(5):  # 尝试几次Tab键
                                ActionChains(driver).send_keys('\ue004').perform()  # \ue004是Tab键
                                time.sleep(0.1)
                            # 发送回车键
                            ActionChains(driver).send_keys('\ue007').perform()  # \ue007是回车键
                            print(f"[{now}] 已尝试键盘提交")
                        except:
                            pass
                else:
                    # 不在订单页面，需要回到订单页面
                    if order_page_url:
                        print(f"[{now}] 不在订单页面，正在返回: {order_page_url}")
                        driver.get(order_page_url)
                        time.sleep(0.5)  # 缩短等待时间
                    else:
                        # 如果没有订单页面记录，尝试快速结算
                        print(f"[{now}] 没有订单页面记录，尝试从购物车快速结算...")
                        driver.get("https://cart.taobao.com/cart.htm")
                        
                        # 使用JS快速选择全部商品和结算
                        fast_checkout_js = """
                        (function() {
                            // 选中全部商品
                            var checkboxes = document.querySelectorAll('input[type="checkbox"]');
                            for(var i=0; i<checkboxes.length; i++) {
                                checkboxes[i].checked = true;
                            }
                            
                            // 点击结算按钮
                            var settlement = document.querySelector('#J_Go, .J_SmallSubmit, [class*="settlement"], [class*="submit-btn"]');
                            if(settlement) {
                                settlement.click();
                                return true;
                            }
                            return false;
                        })();
                        """
                        driver.execute_script(fast_checkout_js)
                        time.sleep(1)
                
                # 检查订单是否成功提交
                time.sleep(0.3)  # 缩短检查时间
                
                # 检查URL是否包含成功特征
                current_url = driver.current_url
                if any(keyword in current_url for keyword in ["buy_success", "trade_id=", "alipay.com", "payment.htm"]):
                    print(f"[{now}] 检测到成功URL特征: {current_url}")
                    submit_succ = True
                
                if submit_succ:
                    print(f"[{now}] 订单提交成功！")
                    play_success_sound()
                    break
                else:
                    # 检查页面内容以识别成功
                    success_text = ["订单提交成功", "付款", "支付宝", "支付"]
                    page_text = driver.page_source
                    if any(text in page_text for text in success_text):
                        print(f"[{now}] 页面内容显示订单可能已成功提交")
                        submit_succ = True
                        play_success_sound()
                        break
                    
                    # 如果仍在订单页面，直接使用JavaScript刷新页面
                    # 这比driver.refresh()更快
                    if "buy.taobao.com" in current_url or "buy.tmall.com" in current_url:
                        print(f"[{now}] 使用快速刷新继续尝试...")
                        driver.execute_script("location.reload(true);")
                    else:
                        print(f"[{now}] 尝试返回订单页面: {order_page_url}")
                        if order_page_url:
                            driver.get(order_page_url)
                        
            except Exception as e:
                print(f"[{now}] 提交订单过程发生错误: {repr(e)}")
                # 如果有订单页面记录，尝试快速返回
                if order_page_url:
                    driver.get(order_page_url)
            
            # 更短的等待时间
            time.sleep(random.uniform(0.05, 0.1))
        else:
            # 未到抢购时间，继续等待
            remaining_seconds = (buy_time_object - now).total_seconds()
            if remaining_seconds < 10:
                print(f"即将开始抢购，倒计时 {remaining_seconds:.2f} 秒...")
            time.sleep(0.01)  # 保持高精度倒计时
    
    if not submit_succ:
        print("抢购尝试结束，未成功提交订单")
    else:
        print("抢购成功！请在24小时内完成订单付款")


def buy():
    """保持原有函数名称兼容性"""
    global order_submit_page_loaded
    
    # 计算开始准备的时间点
    prepare_start_time = buy_time_object - datetime.timedelta(minutes=PREPARE_MINUTES_BEFORE)
    current_time = get_adjusted_time()  # 使用校准时间
    
    # 如果当前时间已经超过预计的准备开始时间，则立即开始准备
    if current_time >= prepare_start_time:
        print(f"当前时间已经进入抢购准备阶段，立即开始准备...")
        prepare_success = prepare_for_purchase()
    else:
        # 否则等待到准备开始时间
        seconds_to_wait = (prepare_start_time - current_time).total_seconds()
        print(f"将在抢购时间前 {PREPARE_MINUTES_BEFORE} 分钟（{prepare_start_time}）开始准备，还需等待 {seconds_to_wait:.2f} 秒...")
        
        # 等待直到准备开始时间
        while get_adjusted_time() < prepare_start_time:
            remaining_wait = (prepare_start_time - get_adjusted_time()).total_seconds()
            if remaining_wait > 60 and remaining_wait % 60 < 1:  # 每分钟提示一次
                print(f"距离开始准备还有 {remaining_wait:.0f} 秒...")
            elif remaining_wait < 60 and remaining_wait % 10 < 1:  # 最后一分钟每10秒提示
                print(f"即将开始准备，还有 {remaining_wait:.0f} 秒...")
            time.sleep(1)
        
        print(f"[{get_adjusted_time()}] 开始准备抢购流程...")
        prepare_success = prepare_for_purchase()
    
    if prepare_success:
        print(f"[{get_adjusted_time()}] 提前准备成功，将在 {BUY_TIME} 准时提交订单")
        
        # 计算距离抢购时间的剩余秒数
        remaining_seconds = (buy_time_object - get_adjusted_time()).total_seconds()
        
        # 如果距离抢购时间还有超过30秒，需要保持页面活跃
        if remaining_seconds > 30:
            print(f"距离抢购时间还有 {remaining_seconds:.2f} 秒，将保持页面活跃...")
            
            next_refresh_time = get_adjusted_time() + datetime.timedelta(seconds=25)
            while get_adjusted_time() < buy_time_object - datetime.timedelta(seconds=15):
                try:
                    # 如果到达刷新时间点，执行页面保活操作
                    if get_adjusted_time() >= next_refresh_time:
                        print(f"[{get_adjusted_time()}] 执行页面保活...")
                        # 尝试执行一些不影响页面状态的操作
                        driver.execute_script("window.scrollTo(0, 0);")
                        
                        # 检查提交按钮是否还有效
                        try:
                            if submit_order_button and (not submit_order_button.is_enabled() or not submit_order_button.is_displayed()):
                                print("提交按钮可能已失效，重新准备...")
                                order_submit_page_loaded = False
                                prepare_for_purchase()
                        except:
                            print("提交按钮状态检查失败，重新准备...")
                            order_submit_page_loaded = False
                            prepare_for_purchase()
                            
                        next_refresh_time = get_adjusted_time() + datetime.timedelta(seconds=25)
                except Exception as e:
                    print(f"保持会话操作失败: {e}，重新准备...")
                    order_submit_page_loaded = False
                    prepare_for_purchase()
                    
                # 更新倒计时显示
                now = get_adjusted_time()
                remaining = (buy_time_object - now).total_seconds()
                if remaining < 60 and int(remaining) % 10 == 0:  # 每10秒更新一次
                    print(f"距离抢购时间还剩 {remaining:.2f} 秒...")
                    
                time.sleep(0.5)  # 避免过度占用CPU
            
        # 进入最后冲刺
        print(f"[{get_adjusted_time()}] 进入最后冲刺阶段...")
        # 最后10秒内再次确认按钮状态
        try:
            if not order_submit_page_loaded or not submit_order_button or not submit_order_button.is_displayed():
                print("最后检查发现提交按钮状态异常，紧急重新准备...")
                prepare_for_purchase()
        except:
            print("最后检查按钮状态失败，紧急重新准备...")
            prepare_for_purchase()
    else:
        print(f"[{get_adjusted_time()}] 提前准备未成功完成，将在抢购时继续尝试")
    
    # 执行抢购
    execute_purchase()


login()
keep_login_and_wait()
buy()
