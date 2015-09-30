# coding=utf-8
import json
import os
import gensim
import requests
import jieba.posseg as pseg
import sys
import DAO_utils

__author__ = 'jayvee'

apath = os.path.dirname(__file__)
sys.path.append(apath)
reload(sys)
sys.setdefaultencoding('utf-8')

weight_map = {u'娱乐-5': {u'追星族': 0.1, u'电视迷': 0.9},
              u'娱乐-9': {u'追星族': 0.7, u'八卦': 0.3},
              u'娱乐-11': {u'追星族': 0.7, u'八卦': 0.3},
              u'互联网-2': {u'互联网业界': 1},
              u'体育-4': {u'体育装备': 0.7, u'体育历史': 0.3},
              u'体育-6': {u'体育新闻': 1},
              u'体育-11': {u'体育装备': 0.2, u'体育历史': 0.8},
              u'军事-10': {u'军事轶事': 1},
              u'军事-11': {u'军事历史': 0.9, u'军事新闻': 0.1}}


def map_atag2utag(atag):
    p = weight_map[atag]
    return p


def update_a_u_map(reaction_list, a_u_map, insert_rate=0.001):
    """
    根据一段时间的交互记录，更新文章tag到用户tag之间的映射权重值
    :param reaction_list:
    :param a_u_map:
    :param insert_rate:
    :return:
    """
    for reaction in reaction_list:
        # process article tags
        reaction_a_id = reaction.reaction_a_id
        article = DAO_utils.get_article_by_id(reaction_a_id)
        article_tags = article.atags
        # get user tags
        reaction_user_id = reaction.reaction_user_id
        user = DAO_utils.get_user_by_id(reaction_user_id)
        utag_vec = user.user_tag_score_vec

        reaction_type = reaction.reaction_type
        reaction_date = reaction.reaction_date
        for atag_key in article_tags:
            # 采用稀释的方式改变映射权值
            atag_value = article_tags[atag_key]  # 文章本身的tag权值，用于衡量该篇文章的属性，0~1之间的值。
            # 首先稀释原有的权值
            a_u_inst = a_u_map[atag_key]
            for ukey in a_u_inst:
                a_u_inst[ukey] *= (1 - insert_rate)
            # 然后insert用户的tags
            for utag_key in utag_vec:
                if utag_key in a_u_inst:
                    a_u_inst[utag_key] += utag_vec[utag_key] * insert_rate * atag_value
                else:
                    a_u_inst[utag_key] = utag_vec[utag_key] * insert_rate * atag_value
        return a_u_map


def passage_first_level_classify(content):
    """
    given a passage content, return its first level class
    :param content:
    :return:
    """
    for i in xrange(3):
        try:
            classify_result = \
                json.loads(requests.post('http://bosonnlp.com/analysis/category', {'data': content}).content)[0]
            class_dict = {0: u'体育', 1: u'教育', 2: u'财经', 3: u'社会',
                          4: u'娱乐', 5: u'军事', 6: u'国内',
                          7: u'科技', 8: '互联网', 9: u'房产', 10: u'国际',
                          11: u'女人', 12: u'汽车', 13: u'游戏'}
            classify_result = class_dict[classify_result]
            return classify_result
        except requests.Timeout, to:
            print to
            continue


def passage_second_level_classify(content):
    """
    given a passage content, return its second level class
    :param content:
    :return: a topic list with probablity
    """
    first_class = passage_first_level_classify(content)
    print first_class
    lda_model = gensim.models.LdaModel.load('%s/wechat_data/lda_in_classify/%s.model' % (apath, first_class))
    word_list = []
    words = pseg.cut(content)
    for item in words:
        if item.flag in [u'n', u'ns']:
            word_list.append(item.word)
    train_set = [word_list]
    dic = gensim.corpora.Dictionary(train_set)
    corpus = [dic.doc2bow(text) for text in train_set]
    doc_lda = lda_model.get_document_topics(corpus)
    count = 0
    # for j in lda_model.print_topics(20):
    #     print count, j
    #     count += 1
    # print doc_lda
    topic_list = []
    for i in lda_model[corpus]:
        for k in i:
            print lda_model.print_topic(k[0], 7), k[1]
            topic_list.append(
                {'topic_tag': u'%s-%s' % (first_class, k[0]), 'topic_content': lda_model.print_topic(k[0], 7),
                 'topic_prob': k[1]})
    return topic_list


def user_tagging(inst_user, reaction_list, reaction_type_weight, a_u_tagmap):
    """
        根据用户一段时间的交互记录，更新用户的u_tag分数
        :param reaction_list:user_id等于当前用户id的一段时间内的交互记录
        :param a_u_tagmap:
        :return:
        """
    user_atag_vec = inst_user.user_atag_vec
    user_tag_score_vec = inst_user.user_tag_score_vec

    for reaction in reaction_list:
        weight = reaction_type_weight[reaction.reaction_type]
        a_id = reaction.reaction_a_id
        # todo a_map just for demo
        article = DAO_utils.get_article_by_id(a_id)
        for a_tag_key in article.a_tags:  # 文章的tags应该是一个dict
            if a_tag_key in user_atag_vec:
                user_atag_vec[a_tag_key] += weight * article.a_tags[a_tag_key]
            else:
                user_atag_vec[a_tag_key] = weight * article.a_tags[a_tag_key]


    # 用户的atag_vec处理完毕，开始处理user_tag_score_vec
    # TODO 更好的权值赋值公式
    for a_tag_key in user_atag_vec.keys():
        for u_tag_key in a_u_tagmap[a_tag_key]:
            if u_tag_key in user_tag_score_vec:  # TODO 是否需要每次都加？
                user_tag_score_vec[u_tag_key] = a_u_tagmap[a_tag_key][u_tag_key] * user_atag_vec[
                    a_tag_key]
            else:
                user_tag_score_vec[u_tag_key] = a_u_tagmap[a_tag_key][u_tag_key] * user_atag_vec[
                    a_tag_key]
    return user_tag_score_vec


def user_tagging_by_reactionlist(reaction_list, reaction_type_weight, a_u_tagmap):
    pass
