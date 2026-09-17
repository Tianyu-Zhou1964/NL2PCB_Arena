# mini_kicad 格式

将由 gendoc 生成

<!-- 占位。本文件作用：
     agent 提交的答案格式，kicad_pcb 的语法子集：只留设计决定，去掉生成物、样式、环境。
     骨架和 GT 也用它落盘；build_kit.py 把本文件原样拷进任务的 assets/ 发给 agent。

     内容：
     - 版本声明：generator 以 nl2pcb 开头时校验 generator_version
     - 节点表：footprint / pad / segment / via / zone / gr_rect|gr_poly|gr_line
     - 坐标与角度约定，pad 的 at 是未旋转偏移、rot 是绝对角
     - 网络靠名字不靠编号
     - 裁剪表：丢弃 / 拒绝两张名单
     - 常见错误 → parse.* 诊断码

     裁剪表的真相来源是 src/nl2pcb/lang/kicad.py 的 _*_DROP 集合，
     本文件对应小节由 dev/gen_mini_kicad_tables.py 生成，不手写维护两份。
     随 lang 层一起落地（PR #2）。
-->
