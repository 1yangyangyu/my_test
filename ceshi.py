#导入pands库
import pandas as pd
##划分训练测试集、交叉验证
from sklearn.model_selection import train_test_split, GridSearchCV
#标准化
from sklearn.preprocessing import StandardScaler
#决策树
from sklearn.tree import DecisionTreeClassifier
#随机森林
from sklearn.ensemble import RandomForestClassifier
#评估
from sklearn.metrics import accuracy_score
#读取数据
df = pd.read_csv('./data/train.csv')
#选取特征
x = df[['Pclass', 'Sex', 'Age']].copy()
#标签
y = df['Survived']
#填充缺失值
x['Age'] = x['Age'].fillna(x['Age'].mean())
#机器学习模型（如决策树、随机森林、逻辑回归等）只能理解数字，无法直接处理文本。
# 这行代码的作用就是将数据集中所有包含文本类别的列，自动转换为模型能看懂的数值格式。
x = pd.get_dummies(x)
#给数据打上标准列名的标签”，确保以后无论来什么样的新数据，都能被转换成和训练时一模一样的格式。
feature_cols = x.columns

x_train, x_test, y_train, y_test = train_test_split(x, y, test_size=0.2, random_state=30)
#初始化决策树
estimator1 = DecisionTreeClassifier()
#拟合，训练
estimator1.fit(x_train, y_train)
#根据测试集输出预测值
y_pred1 = estimator1.predict(x_test)
print('单一决策树预测结果: \n', y_pred1)
print(f'单一决策树的准确率: \n{accuracy_score(y_test, y_pred1)}')
print('♥️' * 10)
#初始化随机森林
estimator2 = RandomForestClassifier()
#训练
estimator2.fit(x_train, y_train)
#根据训练集预测
y_pred2 = estimator2.predict(x_test)
print('默认参数随机森林预测结果: \n', y_pred2)
print(f'随机森林准确率(默认参): \n{accuracy_score(y_test, y_pred2)}')
print('♥️' * 10)
#初始化随机森林
estimator3 = RandomForestClassifier()
params = {'n_estimators': [30, 50, 90, 110, 130], 'max_depth': [2, 5, 7, 8]}
#交叉验证
gs_estimator = GridSearchCV(estimator3, param_grid=params, cv=2)
#训练
gs_estimator.fit(x_train, y_train)
#预测
y_pred3 = gs_estimator.predict(x_test)
print('调参后随机森林预测结果: \n', y_pred3)
print(f'随机森林准确率(调参): \n{accuracy_score(y_test, y_pred3)}')
print(f'最佳参数为: \n{gs_estimator.best_params_}')
print('♥️' * 10)

print("===== 自定义单样本预测结果 =====")
custom_data = {
    "Pclass": [3],
    "Sex": ["male"],
    "Age": [38]
}
custom_df = pd.DataFrame(custom_data)
custom_df = pd.get_dummies(custom_df)
custom_df = custom_df.reindex(columns=feature_cols, fill_value=0)

pred_tree = estimator1.predict(custom_df)
pred_rf_default = estimator2.predict(custom_df)
pred_rf_best = gs_estimator.predict(custom_df)

def parse_res(res):
    return "幸存" if res[0] == 1 else "遇难"

print(f"自定义乘客信息：三等舱、男性、38岁")
print(f"单一决策树预测结果：{parse_res(pred_tree)}")
print(f"默认参数随机森林预测结果：{parse_res(pred_rf_default)}")
print(f"调优后随机森林预测结果：{parse_res(pred_rf_best)}")

