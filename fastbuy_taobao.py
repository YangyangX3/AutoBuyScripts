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

now_time = datetime.datetime.now()
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

    # time.sleep(3)
    now = datetime.datetime.now()
    print("login success:", now.strftime("%Y-%m-%d %H:%M:%S"))


def __refresh_keep_alive():
    # 重新加载购物车页面，定时操作，防止长时间不操作退出登录
    driver.get("https://cart.taobao.com/cart.htm")
    print("刷新购物车界面，防止登录超时...")
    time.sleep(60)


def keep_login_and_wait():
    print("当前距离抢购时间点还有较长时间，开始定时刷新防止登录超时...")
    while True:
        currentTime = datetime.datetime.now()
        if (buy_time_object - currentTime).seconds > 180:
            __refresh_keep_alive()
        else:
            print("抢购时间点将近，停止自动刷新，准备进入抢购阶段...")
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


def buy():
    # 打开购物车
    driver.get("https://cart.taobao.com/cart.htm")
    time.sleep(1) # 等待页面初步加载

    # 点击购物车里全选按钮
    try:
        # 原定位方式:
        # select_all_button = WebDriverWait(driver, 10).until(
        #     EC.presence_of_element_located((By.ID, "J_SelectAll1"))
        # )
        # 备选XPath (修正引号):
        select_all_button = WebDriverWait(driver, 20).until(
            EC.element_to_be_clickable((By.XPATH, "//div[contains(@class, 'cart-select-all') or @id='J_SelectAll1']//input[@type='checkbox'] | //label[contains(.,'全选')]"))
        )
        if not select_all_button.is_selected(): # 如果本身未选中，则点击
             select_all_button.click()
        print("已经选中购物车中全部商品 ...")
    except Exception as e:
        print(f"无法找到或点击全选按钮: {e}")
        # 可以选择在此处退出或采取其他恢复措施
        driver.save_screenshot("error_select_all.png")
        print("已保存截图: error_select_all.png")
        raise # 重新抛出异常，以便外部知道操作失败

    submit_succ = False
    retry_submit_times = 0
    # 增加总的抢购尝试时间上限，例如5分钟
    purchase_timeout = datetime.datetime.now() + datetime.timedelta(minutes=5)

    while datetime.datetime.now() < purchase_timeout:
        now = datetime.datetime.now()
        if now >= buy_time_object:
            # 增加判断，如果已经成功提交了订单，直接跳出循环
            if submit_succ:
                print(f"[{datetime.datetime.now()}] 订单已经提交成功，退出抢购流程...")
                break
                
            print(f"到达抢购时间，开始执行抢购...尝试次数：{retry_submit_times + 1}")
            
            if retry_submit_times > 100: # 增加结算后的重试次数
                print("重试抢购次数达到上限（100次），放弃重试...")
                break

            retry_submit_times += 1

            try:
                # 点击结算按钮
                print(f"[{datetime.datetime.now()}] 尝试定位并点击结算按钮...")
                checkout_button = WebDriverWait(driver, 10).until(
                    EC.element_to_be_clickable((By.XPATH, "//*[@id='settlementContainer_1']/div[4]/div/div[2] | //div[@id='J_Go'] | //a[contains(text(), '结 算')] | //button[contains(text(), '结 算')]"))
                )
                checkout_button.click()
                print(f"[{datetime.datetime.now()}] 已经点击结算按钮...")

                # ---- 同意协议复选框处理 ----
                time.sleep(1) # 等待订单提交页面加载一些基本元素
                if CHECK_AGREEMENT_CHECKBOX:
                    try:
                        print(f"[{datetime.datetime.now()}] 尝试定位并勾选同意协议复选框...")
                        # 增加多种可能的复选框XPath定位方式
                        agree_checkbox_xpath = "//*[@id='submitOrderPC_1']/div/div/label/input | //input[contains(@id, 'agreement')] | //input[@type='checkbox'][contains(@id, 'agree')]"
                        agree_checkbox = WebDriverWait(driver, 10).until(
                            EC.element_to_be_clickable((By.XPATH, agree_checkbox_xpath))
                        )
                        
                        if not agree_checkbox.is_selected():
                            agree_checkbox.click()
                            print(f"[{datetime.datetime.now()}] 已勾选同意协议复选框。")
                        else:
                            print(f"[{datetime.datetime.now()}] 同意协议复选框已被勾选。")
                        time.sleep(0.3)
                    except TimeoutException:
                        print(f"[{datetime.datetime.now()}] 定位同意协议复选框超时，可能不存在此元素。")
                    except Exception as e_agree:
                        print(f"[{datetime.datetime.now()}] 处理同意协议复选框时发生其他错误: {repr(e_agree)}")
                else:
                    print(f"[{datetime.datetime.now()}] 已设置跳过同意协议复选框检查")
                # ---- 同意协议复选框处理结束 ----

                # 支持多种提交订单按钮的XPath
                print(f"[{datetime.datetime.now()}] 尝试定位并点击提交订单按钮...")
                submit_button_xpaths = [
                    "//a[contains(text(),'提交订单')] | //button[contains(text(),'提交订单')]",
                    "//*[@id='submitOrder']/div/div[2]/div",  # 新增用户提供的XPath
                    "//div[contains(@class,'submit-btn')] | //button[contains(@class,'submit')]",
                    "//a[@id='submitOrderPC_1'] | //button[@id='submitOrderPC_1']"
                ]
                
                # 尝试多种XPath定位提交订单按钮
                submit_order_button = None
                for xpath in submit_button_xpaths:
                    try:
                        print(f"[{datetime.datetime.now()}] 尝试使用XPath定位提交按钮: {xpath}")
                        submit_order_button = WebDriverWait(driver, 5).until(
                            EC.element_to_be_clickable((By.XPATH, xpath))
                        )
                        if submit_order_button:
                            print(f"[{datetime.datetime.now()}] 成功找到提交订单按钮，使用XPath: {xpath}")
                            break
                    except Exception as e_btn:
                        print(f"[{datetime.datetime.now()}] 使用XPath '{xpath}'未找到按钮: {repr(e_btn)}")
                        continue
                
                if submit_order_button:
                    submit_order_button.click()
                    print(f"[{datetime.datetime.now()}] 已经点击提交订单按钮")
                    
                    # ---- 订单提交成功性检查部分保持不变 ----
                    time.sleep(1.5)
                    print(f"[{datetime.datetime.now()}] 开始检查订单是否成功提交...")
                    driver.save_screenshot(f"submit_clicked_page_retry_{retry_submit_times}.png")
                    
                    # 扩展成功页面URL关键字列表，增加更多可能的成功页面URL特征
                    expected_url_keywords = [
                        "buy.tmall.com/auction/buy_success.htm", 
                        "trade/detail/trade_item_detail.htm", 
                        "order_detail.htm", 
                        "trade_id=",
                        "alipay.com", # 支付宝支付页面
                        "payment.htm"  # 付款页面
                    ]
                    current_url = driver.current_url
                    print(f"[{datetime.datetime.now()}] 当前URL: {current_url}")
                    
                    order_confirmed_success = False
                    for keyword in expected_url_keywords:
                        if keyword in current_url:
                            order_confirmed_success = True
                            print(f"[{datetime.datetime.now()}] URL中发现成功关键字 '{keyword}', 初步判断订单提交成功。")
                            break
                    
                    if order_confirmed_success:
                        # 可以进一步检查页面是否包含特定成功文本，作为双重确认
                        # success_texts = ["订单提交成功", "已下单", "等待买家付款"]
                        # page_source = driver.page_source
                        # for stext in success_texts:
                        #     if stext in page_source:
                        #         print(f"页面发现成功文本 '{stext}', 再次确认订单提交成功。")
                        #         submit_succ = True
                        #         break
                        # if not submit_succ:
                        #     print(f"[{datetime.datetime.now()}] URL符合但未找到特定成功文本，标记为可能失败以便重试。")
                        #     submit_succ = False # 如果严格要求文本验证
                        submit_succ = True # 如果仅URL检查足够
                    else:
                        print(f"[{datetime.datetime.now()}] URL未匹配到成功关键字，判断订单提交可能未成功或仍在处理。")
                        submit_succ = False
                        driver.save_screenshot(f"submit_url_check_failed_retry_{retry_submit_times}.png")
                        print(f"已保存截图(URL检查失败): submit_url_check_failed_retry_{retry_submit_times}.png")

                    # ---- 订单提交成功性检查结束 ----

                    if submit_succ:
                        print(f"[{datetime.datetime.now()}] 订单提交成功确认！脚本将结束抢购。")
                        play_success_sound()  # 播放提示音
                        break
                    else:
                        print(f"[{datetime.datetime.now()}] 订单提交未最终确认，继续尝试或等待下次重试。")

                else:
                    print(f"[{datetime.datetime.now()}] 尝试了所有已知的提交订单按钮XPath，但均未找到可点击的按钮")
                    driver.save_screenshot(f"submit_button_not_found_retry_{retry_submit_times}.png")
                    # 可以选择返回购物车重试或等待下一轮循环

            except TimeoutException as te:
                print(f"[{datetime.datetime.now()}] 定位元素超时: {repr(te)}")
                driver.save_screenshot(f"error_timeout_retry_{retry_submit_times}.png")
                print(f"已保存截图: error_timeout_retry_{retry_submit_times}.png")
            except Exception as e:
                print(f"[{datetime.datetime.now()}] 尝试提交订单时发生错误 (类型: {type(e).__name__}): {repr(e)}")
                driver.save_screenshot(f"error_submit_order_retry_{retry_submit_times}.png")
                print(f"已保存截图: error_submit_order_retry_{retry_submit_times}.png")
                # 如果是结算后找不到提交订单按钮，可能需要返回购物车重试，或者刷新当前页面
                # 这里简单地继续外层循环，依赖抢购时间到达后的重试
                if "J_Go" in str(e) or "结 算" in str(e): # 如果是结算按钮找不到了，可能需要重新加载购物车
                    print("结算按钮查找失败，尝试返回购物车并重新开始结算流程。")
                    driver.get("https://cart.taobao.com/cart.htm")
                    time.sleep(1) # 等待购物车加载
                    # 可能需要重新执行全选操作
                    try:
                        select_all_button = WebDriverWait(driver, 20).until(
                            EC.element_to_be_clickable((By.XPATH, "//div[contains(@class, 'cart-select-all') or @id='J_SelectAll1']//input[@type='checkbox'] | //label[contains(.,'全选')]"))
                        )
                        if not select_all_button.is_selected():
                             select_all_button.click()
                        print("重新选中购物车中全部商品 ...")
                    except Exception as e_sa_retry:
                        print(f"返回购物车后重新全选失败: {e_sa_retry}")
                        # 此时可能问题比较严重，可以选择退出或等待外层循环超时
                # 短暂休眠，避免过于频繁的无效尝试
                time.sleep(random.uniform(0.5, 1.5))

        # 在循环顶部也检查提交状态，避免时间未到的情况下也被重试
        elif submit_succ:
            print(f"[{datetime.datetime.now()}] 订单已经提交成功，退出抢购流程...")
            break
            
        time.sleep(0.05) # 调整抢购时间检查的频率，原0.1秒可能过于频繁

    if not submit_succ:
        print("抢购时间已过或重试次数已达上限，但订单未成功提交。")
    else:
        print("抢购流程结束，订单已成功提交。")
        # 可以在这里添加提示用户付款的信息
        print("请在24小时内完成订单付款操作。")


login()
keep_login_and_wait()
buy()
