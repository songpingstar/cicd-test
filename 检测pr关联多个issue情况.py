import requests


def get_pr_closing_issues(token, repo_full_name, pr_number):
    """
    查询指定 PR 关联并关闭的 Issue 列表。
    
    :param token: GitHub Personal Access Token
    :param repo_full_name: 仓库全名，例如 'Flexget/Flexget'
    :param pr_number: PR 编号 (int)
    :return: 包含 totalCount 和 nodes 的字典
    """
    headers = {"Authorization": f"Bearer {token}"}
    
    try:
        owner, repo_name = repo_full_name.split('/')
    except ValueError:
        print("❌ 仓库名称格式错误，应为 'Owner/Repo' 格式")
        return None
    
    query = """
    query {
      repository(owner: "%s", name: "%s") {
        pullRequest(number: %d) {
          closingIssuesReferences(first: 10) {
            totalCount
            nodes {
              number
              url
            }
          }
        }
      }
    }
    """ % (owner, repo_name, pr_number)

    try:
        response = requests.post('https://api.github.com/graphql', json={'query': query}, headers=headers)
        
        # 检查 HTTP 状态码
        if response.status_code != 200:
            print(f"❌ 请求失败，HTTP 状态码: {response.status_code}")
            return None
            
        data = response.json()
        
        # 检查 GraphQL 返回的错误
        if 'errors' in data:
            print("❌ GraphQL 查询返回错误:", data['errors'])
            return None
            
        # 提取核心数据
        return data['data']['repository']['pullRequest']['closingIssuesReferences']

    except KeyError:
        print("❌ 解析数据出错，可能是 PR 编号不存在或 Token 权限不足")
        return None
    except Exception as e:
        print(f"❌ 发生未知错误: {e}")
        return None




if __name__ == "__main__":
    token = ""
    repo = 'aesara-devs/aesara'
    number = 1493  # PR 编号
    result = get_pr_closing_issues(token, repo, number)
    print(result)