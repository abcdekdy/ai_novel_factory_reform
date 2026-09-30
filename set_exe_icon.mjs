/**
 * 把图标写入 Windows 可执行文件的 PE 资源。
 *
 * 为什么需要它：Electron 的 BrowserWindow({icon}) 只影响窗口/任务栏图标，
 * **资源管理器里看到的 exe 文件图标来自 PE 资源**，必须另行改写。没有这一步，
 * 用户解压后在文件夹里看到的是 Electron 默认的原子标。
 *
 * 用法：node set_exe_icon.mjs <exe路径> <ico路径>
 * 由 package_portable.py 在组装完成后调用。
 *
 * 注意：rcedit v4+ 是 ESM 模块，只能 import；且它是**命名导出** `rcedit`，
 * 没有 default 导出（写成 `import rcedit from 'rcedit'` 会直接抛 SyntaxError）。
 */
import { rcedit } from 'rcedit'

const [exePath, iconPath] = process.argv.slice(2)
if (!exePath || !iconPath) {
  console.error('用法: node set_exe_icon.mjs <exe路径> <ico路径>')
  process.exit(1)
}

try {
  await rcedit(exePath, { icon: iconPath })
  console.log(`已写入 exe 图标: ${exePath}`)
} catch (err) {
  // 图标是锦上添花，失败不应中断整个打包流程
  console.error(`写入 exe 图标失败（不影响程序运行）: ${err.message}`)
  process.exit(0)
}
