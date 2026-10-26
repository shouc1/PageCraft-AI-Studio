# 即梦 workflow 说明
> 用于 Agent 判断 text2image / image2image 的适用场景和参数约束。

---

## workflow：text2image
- 适用场景：用户只有文字需求，没有上传商品图或参考图。
- 典型需求：生成电商海报、节日促销图、场景概念图。
- 输入要求：positive prompt、输出尺寸。
- 风险：商品外观不可控，容易生成不存在的商品或错误品牌。
- Agent 决策：无 input_image 时选择。

---

## workflow：image2image
- 适用场景：用户上传商品图，希望保留商品主体并替换背景、光影、氛围或风格。
- 典型需求：商品图美化、背景替换、电商主图风格化。
- 输入要求：input_image、positive prompt、输出尺寸、strength。
- prompt 要求：必须强调保留原图产品外观、品牌标识、材质和结构，不改变产品形态。
- Agent 决策：有 input_image 时选择。

---

## workflow 选择优先级
1. 用户显式选择合法 workflow 时，尊重用户选择。
2. 如果存在 input_image，选择 image2image。
3. 否则选择 text2image。
