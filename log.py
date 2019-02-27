# 静态调用的日志类 by:rayiooo

import os
import time

class Log:
    level = 2

    # 所有logout输出时都调用此方法
    def logout(type, content):
        log_content = Log.getCurrentTimeFormat() + ' ' + type + ': ' + content
        print(log_content)

    # long
    def l(self, content):
        if Log.level <= 0:
            Log.logout('[LONG]', content)

    # debug
    def d(content):
        if Log.level <= 1:
            Log.logout('[DEBUG]', content)

    # info
    def i(content):
        if Log.level <= 2:
            Log.logout('[INFO]', content)

    # warning
    def w(content):
        if Log.level <= 3:
            Log.logout('[WARN]', content)

    # error
    def e(content):
        if Log.level <= 4:
            Log.logout('[ERROR]', content)

    # fatal
    def f(content):
        if self.level <= 5:
            self.logout('[FATAL]', content)

    # get time
    def getCurrentTimeFormat(type='normal'):
        if type == 'no_invalid':
            return time.strftime('%Y-%m-%d %H%M%S', time.localtime(time.time()))
        return time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(time.time()))


if __name__ == '__main__':
    Log.i('信息')
    Log.d('测试')
    Log.e('出错啦')
